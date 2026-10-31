#![forbid(unsafe_code)]

use std::collections::HashMap;
use std::path::PathBuf;
use std::time::UNIX_EPOCH;

use async_trait::async_trait;
use minidump::{Minidump, Module as MinidumpModule};
use minidump_unwind::{
    FileError, FileKind, FillSymbolError, FrameSymbolizer, FrameWalker, SymbolFile, SymbolProvider,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::pybacked::PyBackedBytes;
use pyo3::types::{PyBytes, PyTuple};
use symbolic_cfi::CfiCache;
use symbolic_common::DebugId;
use symbolic_debuginfo::{Archive, Object};
use symbolic_demangle::{Demangle, DemangleOptions};
use symbolic_symcache::{SymCache, SymCacheConverter};

fn invalid(error: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(error.to_string())
}

// Keep the archive and borrowed object inside the call, including when the file has multiple objects.
fn with_object<T>(data: &[u8], operation: impl FnOnce(&Object<'_>) -> PyResult<T>) -> PyResult<T> {
    if data.starts_with(b"SYSB") {
        return Err(invalid("Expected debug information, got a source bundle"));
    }
    let archive = Archive::parse(data).map_err(invalid)?;
    if archive.object_count() != 1 {
        return Err(invalid("Expected exactly one debug object"));
    }
    let object = archive
        .object_by_index(0)
        .map_err(invalid)?
        .ok_or_else(|| invalid("Missing debug object"))?;
    operation(&object)
}

#[pyfunction]
fn debug_file_kind(py: Python<'_>, data: &[u8]) -> PyResult<String> {
    py.detach(|| with_object(data, |object| Ok(object.kind().to_string())))
}

#[pyfunction]
fn generate_cfi<'py>(py: Python<'py>, data: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    let cache = py.detach(|| {
        with_object(data, |object| {
            CfiCache::from_object(object).map_err(invalid)
        })
    })?;
    Ok(PyBytes::new(py, cache.as_slice()))
}

#[pyclass(get_all, frozen, module = "symalot")]
struct SourceLocation {
    function_name: String,
    filename: Option<String>,
    line: u32,
}

/// Look up a batch of module-relative addresses, preserving order and all inline locations.
#[pyfunction]
fn lookup_addresses(
    py: Python<'_>,
    data: &[u8],
    addresses: Vec<u64>,
) -> PyResult<Vec<Vec<SourceLocation>>> {
    py.detach(|| {
        with_object(data, |object| {
            let mut converter = SymCacheConverter::new();
            converter.process_object(object).map_err(invalid)?;
            let mut bytes = Vec::new();
            converter.serialize(&mut bytes).map_err(invalid)?;
            let cache = SymCache::parse(&bytes).map_err(invalid)?;
            Ok(addresses
                .into_iter()
                .map(|address| {
                    cache
                        .lookup(address)
                        .map(|location| SourceLocation {
                            function_name: location
                                .function()
                                .name_for_demangling()
                                .try_demangle(DemangleOptions::complete())
                                .into_owned(),
                            filename: location.file().map(|file| file.full_path()),
                            line: location.line(),
                        })
                        .collect()
                })
                .collect())
        })
    })
}

#[pyfunction]
fn normalize_debug_id(value: &str) -> PyResult<String> {
    Ok(value.parse::<DebugId>().map_err(invalid)?.to_string())
}

#[pyclass(get_all, frozen, module = "symalot")]
struct Frame {
    instruction: u64,
    trust: String,
}

#[pyclass(get_all, frozen, module = "symalot")]
struct Thread {
    thread_id: u32,
    frames: Py<PyTuple>,
}

#[pyclass(get_all, frozen, module = "symalot")]
struct Module {
    addr: u64,
    size: u64,
    debug_id: Option<String>,
    code_id: Option<String>,
    code_file: String,
    debug_file: Option<String>,
}

#[pyclass(get_all, frozen, module = "symalot")]
struct SystemInfo {
    os_name: String,
    os_version: Option<String>,
    cpu: String,
}

#[pyclass(get_all, frozen, module = "symalot")]
struct ProcessState {
    timestamp: u64,
    crashed: bool,
    crash_reason: Option<String>,
    assertion: Option<String>,
    requesting_thread: Option<usize>,
    system_info: Py<SystemInfo>,
    modules: Py<PyTuple>,
    threads: Py<PyTuple>,
}

struct CfiSymbols(HashMap<DebugId, SymbolFile>);

#[async_trait]
impl SymbolProvider for CfiSymbols {
    async fn fill_symbol(
        &self,
        _module: &(dyn MinidumpModule + Sync),
        _frame: &mut (dyn FrameSymbolizer + Send),
    ) -> Result<(), FillSymbolError> {
        // CFI has no function names; symbolication is a separate batch operation.
        Err(FillSymbolError {})
    }

    async fn walk_frame(
        &self,
        module: &(dyn MinidumpModule + Sync),
        walker: &mut (dyn FrameWalker + Send),
    ) -> Option<()> {
        self.0
            .get(&module.debug_identifier()?)?
            .walk_frame(module, walker)
    }

    async fn get_file_path(
        &self,
        _module: &(dyn MinidumpModule + Sync),
        _kind: FileKind,
    ) -> Result<PathBuf, FileError> {
        Err(FileError::NotFound)
    }
}

/// Process a dump with an optional mapping of debug IDs to ASCII CFI bytes. No file or network access.
#[pyfunction]
#[pyo3(signature = (data, cfi=None))]
fn process_minidump(
    py: Python<'_>,
    data: &[u8],
    cfi: Option<HashMap<String, PyBackedBytes>>,
) -> PyResult<ProcessState> {
    let state = py.detach(|| {
        let mut symbols = HashMap::new();
        for (id, bytes) in cfi.unwrap_or_default() {
            let id = id.parse::<DebugId>().map_err(invalid)?;
            if bytes.is_empty() {
                continue;
            }
            symbols.insert(
                id,
                SymbolFile::parse(bytes.as_ref(), |_| {}).map_err(invalid)?,
            );
        }
        let dump = Minidump::read(data).map_err(invalid)?;
        let runtime = tokio::runtime::Builder::new_current_thread()
            .build()
            .map_err(invalid)?;
        runtime
            .block_on(minidump_processor::process_minidump(
                &dump,
                &CfiSymbols(symbols),
            ))
            .map_err(invalid)
    })?;
    let crashed = state.crashed();
    let threads = state
        .threads
        .into_iter()
        .map(|thread| {
            let frames = PyTuple::new(
                py,
                thread.frames.into_iter().map(|frame| Frame {
                    instruction: frame.instruction,
                    trust: frame.trust.as_str().to_owned(),
                }),
            )?;
            Ok(Thread {
                thread_id: thread.thread_id,
                frames: frames.unbind(),
            })
        })
        .collect::<PyResult<Vec<_>>>()?;
    let modules: Vec<_> = state
        .modules
        .iter()
        .map(|module| Module {
            addr: module.base_address(),
            size: module.size(),
            debug_id: module.debug_identifier().map(|id| id.to_string()),
            code_id: module.code_identifier().map(|id| id.to_string()),
            code_file: module.code_file().into_owned(),
            debug_file: module.debug_file().map(|file| file.into_owned()),
        })
        .collect();
    Ok(ProcessState {
        timestamp: state
            .time
            .duration_since(UNIX_EPOCH)
            .map_err(invalid)?
            .as_secs(),
        crashed,
        crash_reason: state
            .exception_info
            .as_ref()
            .map(|info| info.reason.to_string()),
        assertion: state.assertion,
        requesting_thread: state.requesting_thread,
        system_info: Py::new(
            py,
            SystemInfo {
                os_name: state.system_info.os.long_name().into_owned(),
                os_version: state.system_info.os_version,
                cpu: state.system_info.cpu.to_string(),
            },
        )?,
        modules: PyTuple::new(py, modules)?.unbind(),
        threads: PyTuple::new(py, threads)?.unbind(),
    })
}

#[pymodule]
fn symalot(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(debug_file_kind, module)?)?;
    module.add_function(wrap_pyfunction!(generate_cfi, module)?)?;
    module.add_function(wrap_pyfunction!(lookup_addresses, module)?)?;
    module.add_function(wrap_pyfunction!(normalize_debug_id, module)?)?;
    module.add_function(wrap_pyfunction!(process_minidump, module)?)?;
    module.add_class::<SourceLocation>()?;
    module.add_class::<Frame>()?;
    module.add_class::<Thread>()?;
    module.add_class::<Module>()?;
    module.add_class::<SystemInfo>()?;
    module.add_class::<ProcessState>()?;
    Ok(())
}
