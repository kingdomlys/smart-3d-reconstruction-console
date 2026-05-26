import { useEffect, useMemo, useState } from "react";
import TaskViewer from "./components/TaskViewer.jsx";

const DEFAULT_API = "http://127.0.0.1:8000";

function toWebSocketUrl(httpUrl) {
  return httpUrl.replace(/^http/, "ws");
}

export default function App() {
  const apiBase = import.meta.env.VITE_API_BASE || DEFAULT_API;
  const [files, setFiles] = useState([]);
  const [taskId, setTaskId] = useState("");
  const [status, setStatus] = useState("Idle");
  const [event, setEvent] = useState(null);
  const [outputUrl, setOutputUrl] = useState("");
  const [outputPath, setOutputPath] = useState("");

  const wsBase = useMemo(() => toWebSocketUrl(apiBase), [apiBase]);

  useEffect(() => {
    if (!taskId) {
      return;
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
        if (payload.status === "Completed") {
          fetchOutput(taskId, apiBase);
        }
      } catch (err) {
        console.error(err);
      }
    };
    return () => socket.close();
  }, [taskId, wsBase, apiBase]);

  useEffect(() => {
    return () => {
      if (outputUrl) {
        URL.revokeObjectURL(outputUrl);
      }
    };
  }, [outputUrl]);

  async function fetchOutput(id, base) {
    const response = await fetch(`${base}/api/tasks/${id}/output`);
    if (!response.ok) {
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    setOutputUrl(url);
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
      const err = await response.json();
      setStatus(err.detail?.error || "Upload failed");
      return;
    }

    const payload = await response.json();
    setTaskId(payload.id);
    setStatus(payload.status || "Queued");
    setOutputUrl("");
    setOutputPath("");
  }

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">Local 3D Reconstruction Console</p>
          <h1>Build, route, and preview 3D assets in one place.</h1>
          <p className="subtext">
            Upload images, track progress, and preview GLB outputs in the same
            console.
          </p>
        </div>
        <div className="status-card">
          <span className="label">Task Status</span>
          <strong>{status}</strong>
          {event && (
            <p className="event">
              {event.step || "Update"} · {Math.round((event.progress || 0) * 100)}%
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
            <p>Task ID: {taskId || "—"}</p>
            <p>Output: {outputPath || "—"}</p>
          </div>
        </section>

        <section className="panel viewer">
          <h2>Preview</h2>
          <TaskViewer outputUrl={outputUrl} outputPath={outputPath} />
        </section>
      </main>
    </div>
  );
}
