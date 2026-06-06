import { useEffect, useMemo, useState } from "react";
import TaskViewer from "./components/TaskViewer.jsx";

const DEFAULT_API = "http://127.0.0.1:8000";
const PREVIEW_TYPE_PRIORITY = ["glb", "ply"];

function toWebSocketUrl(httpUrl) {
  return httpUrl.replace(/^http/, "ws");
}

function formatSize(bytes) {
  if (!bytes) {
    return "0 KB";
  }
  if (bytes < 1024 * 1024) {
    return `${Math.ceil(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function selectPreviewOutput(items) {
  for (const type of PREVIEW_TYPE_PRIORITY) {
    const match = items.find((item) => item.type === type);
    if (match) {
      return match;
    }
  }
  return null;
}

export default function App() {
  const apiBase = import.meta.env.VITE_API_BASE || DEFAULT_API;
  const [files, setFiles] = useState([]);
  const [taskId, setTaskId] = useState("");
  const [status, setStatus] = useState("Idle");
  const [event, setEvent] = useState(null);
  const [outputUrl, setOutputUrl] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [outputs, setOutputs] = useState([]);
  const [previewOutput, setPreviewOutput] = useState(null);
  const [logs, setLogs] = useState("");
  const [error, setError] = useState("");
  const [tasks, setTasks] = useState([]);

  const wsBase = useMemo(() => toWebSocketUrl(apiBase), [apiBase]);
  const selectedTask = tasks.find((task) => task.id === taskId);
  const canRetry =
    taskId && selectedTask && !["Pending", "Running"].includes(selectedTask.status);
  const canCancel =
    taskId && selectedTask && ["Pending", "Running"].includes(selectedTask.status);

  useEffect(() => {
    if (!taskId) {
      return undefined;
    }
    const socket = new WebSocket(`${wsBase}/ws/tasks/${taskId}`);
    socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data);
        setEvent(payload);
        if (payload.status) {
          setStatus(payload.status);
        }
        if (payload.output_path) {
          setOutputPath(payload.output_path);
        }
        if (payload.outputs) {
          setOutputs(payload.outputs);
        }
        if (payload.error) {
          setError(payload.error);
        }
        if (payload.status === "Completed") {
          refreshTaskDetails(taskId);
        }
      } catch (err) {
        console.error(err);
      }
    };
    return () => socket.close();
  }, [taskId, wsBase, apiBase]);

  useEffect(() => {
    loadTasks();
  }, []);

  useEffect(() => {
    return () => {
      if (outputUrl) {
        URL.revokeObjectURL(outputUrl);
      }
    };
  }, [outputUrl]);

  async function fetchPreviewOutput(items) {
    const preview = selectPreviewOutput(items);
    setPreviewOutput(preview);
    if (!preview) {
      setOutputUrl("");
      return;
    }

    const response = await fetch(`${apiBase}${preview.download_url}`);
    if (!response.ok) {
      setOutputUrl("");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    setOutputUrl(url);
  }

  async function fetchOutputs(id) {
    const response = await fetch(`${apiBase}/api/tasks/${id}/outputs`);
    if (!response.ok) {
      setOutputs([]);
      return [];
    }
    const payload = await response.json();
    const items = payload.items || [];
    setOutputs(items);
    return items;
  }

  async function fetchLogs(id) {
    const response = await fetch(`${apiBase}/api/tasks/${id}/logs`);
    if (!response.ok) {
      setLogs("");
      return;
    }
    setLogs(await response.text());
  }

  async function refreshTaskDetails(id) {
    const items = await fetchOutputs(id);
    await Promise.all([fetchPreviewOutput(items), fetchLogs(id), loadTasks()]);
  }

  async function loadTasks() {
    const response = await fetch(`${apiBase}/api/tasks?limit=20`);
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    setTasks(payload.items || []);
  }

  async function selectTask(task) {
    setTaskId(task.id);
    setStatus(task.status || "Queued");
    setOutputPath(task.output_path || "");
    setError(task.error || "");
    setOutputUrl("");
    setPreviewOutput(null);
    setOutputs([]);
    setLogs("");
    const items = await fetchOutputs(task.id);
    await Promise.all([fetchPreviewOutput(items), fetchLogs(task.id)]);
  }

  async function retryTask() {
    if (!taskId) {
      return;
    }
    setStatus("Pending");
    setError("");
    const response = await fetch(`${apiBase}/api/tasks/${taskId}/retry`, {
      method: "POST"
    });
    if (!response.ok) {
      const payload = await response.json();
      setStatus(payload.detail || "Retry failed");
      return;
    }
    const payload = await response.json();
    setStatus(payload.status || "Pending");
    setOutputPath(payload.output_path || "");
    setOutputUrl("");
    setPreviewOutput(null);
    setOutputs([]);
    await loadTasks();
  }

  async function cancelTask() {
    if (!taskId) {
      return;
    }
    const response = await fetch(`${apiBase}/api/tasks/${taskId}/cancel`, {
      method: "POST"
    });
    if (!response.ok) {
      const payload = await response.json();
      setError(payload.detail || "Cancel failed");
      return;
    }
    const payload = await response.json();
    setStatus(payload.status || "Canceled");
    setError(payload.error || "");
    setOutputPath(payload.output_path || "");
    await Promise.all([fetchLogs(taskId), loadTasks()]);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!files.length) {
      setStatus("No files selected");
      return;
    }
    setStatus("Uploading");
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    const response = await fetch(`${apiBase}/api/tasks`, {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      const payload = await response.json();
      setStatus(payload.detail?.error || "Upload failed");
      setError(payload.detail?.hint || "");
      return;
    }

    const payload = await response.json();
    setTaskId(payload.id);
    setStatus(payload.status || "Queued");
    setOutputUrl("");
    setOutputPath("");
    setPreviewOutput(null);
    setOutputs([]);
    setLogs("");
    setError("");
    loadTasks();
  }

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local 3D Reconstruction Console</p>
          <h1>3D Reconstruction Control Plane</h1>
        </div>
        <div className="status-strip">
          <span>Status</span>
          <strong>{status}</strong>
          {event && (
            <p>
              {event.step || "Update"} - {Math.round((event.progress || 0) * 100)}%
            </p>
          )}
        </div>
      </header>

      <main className="grid">
        <section className="panel">
          <h2>Upload</h2>
          <form onSubmit={handleSubmit} className="form">
            <input
              type="file"
              accept=".png,.jpg,.jpeg,.webp"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files || []))}
            />
            <button type="submit">Start Task</button>
          </form>
          <div className="meta">
            <p>Task ID: {taskId || "-"}</p>
            <p>Output: {outputPath || "-"}</p>
            {error && <p className="error">Error: {error}</p>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Recent Tasks</h2>
            <div className="actions">
              <button type="button" className="ghost" onClick={loadTasks}>
                Refresh
              </button>
              <button type="button" className="ghost" onClick={retryTask} disabled={!canRetry}>
                Retry
              </button>
              <button type="button" className="ghost danger" onClick={cancelTask} disabled={!canCancel}>
                Cancel
              </button>
            </div>
          </div>
          <div className="task-list">
            {tasks.length === 0 && <p className="muted">No tasks yet.</p>}
            {tasks.map((task) => (
              <button
                key={task.id}
                type="button"
                className={`task-row ${task.id === taskId ? "active" : ""}`}
                onClick={() => selectTask(task)}
              >
                <span>{task.id.slice(0, 8)}</span>
                <span>{task.status}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="panel viewer">
          <h2>Preview</h2>
          <TaskViewer outputUrl={outputUrl} output={previewOutput} />
        </section>

        <section className="panel outputs">
          <h2>Outputs</h2>
          {outputs.length === 0 && <p className="muted">No output files yet.</p>}
          {outputs.length > 0 && (
            <div className="output-list">
              {outputs.map((item) => (
                <a
                  key={item.relative_path}
                  href={`${apiBase}${item.download_url}`}
                  className="output-row"
                  download
                >
                  <span>{item.name}</span>
                  <span>
                    {item.type} - {formatSize(item.size)}
                  </span>
                </a>
              ))}
            </div>
          )}
        </section>

        <section className="panel logs">
          <div className="panel-header">
            <h2>Logs</h2>
            <button type="button" className="ghost" onClick={() => taskId && fetchLogs(taskId)}>
              Refresh
            </button>
          </div>
          <pre>{logs || "No logs yet."}</pre>
        </section>
      </main>
    </div>
  );
}
