import { useEffect, useRef, useState } from "react";
import { Mic, Square, Volume2, X } from "lucide-react";
import { errorMessage, rawRequest } from "./api";

export function Dictation({ csrf, disabled, insert }: {
  csrf: string; disabled: boolean; insert: (text: string) => void;
}) {
  const [phase, setPhase] = useState<"opening" | "recording" | "transcribing">();
  const [mode, setMode] = useState("auto");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const active = useRef<MediaRecorder>(null);
  const request = useRef<AbortController>(null);
  const generation = useRef(0);

  function release() {
    generation.current++;
    request.current?.abort();
    const recorder = active.current;
    active.current = null;
    if (recorder?.state === "recording") recorder.stop();
    recorder?.stream.getTracks().forEach((track) => track.stop());
  }

  useEffect(() => release, []);
  useEffect(() => {
    if (phase !== "recording") return;
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 250);
    const limit = window.setTimeout(() => {
      if (active.current?.state === "recording") active.current.stop();
    }, 29000);
    return () => { clearInterval(timer); clearTimeout(limit); };
  }, [phase]);

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Microphone recording is unavailable in this browser."); return;
    }
    const turn = ++generation.current;
    setError(""); setPhase("opening");
    let stream: MediaStream | undefined;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (generation.current !== turn) { stream.getTracks().forEach((track) => track.stop()); return; }
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      active.current = recorder;
      const parts: Blob[] = [];
      recorder.ondataavailable = ({ data }) => { if (data.size) parts.push(data); };
      recorder.onerror = () => {
        if (generation.current !== turn) return;
        release(); setPhase(undefined); setError("Recording failed. Try again.");
      };
      recorder.onstop = async () => {
        recorder.stream.getTracks().forEach((track) => track.stop());
        if (generation.current !== turn) return;
        active.current = null;
        setPhase("transcribing");
        const controller = new AbortController();
        request.current = controller;
        try {
          const type = (recorder.mimeType || parts[0]?.type || "").split(";")[0];
          const response = await rawRequest(`/voice/transcribe?mode=${mode}`, {
            method: "POST", headers: { "Content-Type": type, "X-CSRF-Token": csrf },
            body: new Blob(parts, { type }), signal: controller.signal,
          });
          const { text, warning } = await response.json() as { text: string; warning?: string };
          if (generation.current === turn) {
            if (text.trim()) { insert(text); if (warning) setError(warning); }
            else setError("No speech detected. Try another recording.");
          }
        } catch (error) { if (generation.current === turn) setError(errorMessage(error) === "Not Found" ? "Voice API unavailable. Restart the updated Timmy API." : errorMessage(error)); }
        finally { if (generation.current === turn) setPhase(undefined); }
      };
      recorder.start();
      setSeconds(0); setPhase("recording");
    } catch {
      stream?.getTracks().forEach((track) => track.stop());
      if (generation.current === turn) { setPhase(undefined); setError("Microphone access failed. Check your browser permissions."); }
    }
  }

  return <div className="voice-controls">
    <select aria-label="Voice language and script" value={mode} disabled={!!phase || disabled}
      onChange={(event) => setMode(event.target.value)}>
      <option value="auto">Auto</option><option value="en">English</option><option value="ar">العربية</option><option value="arabizi">Arabizi</option>
    </select>
    {!phase && <button type="button" className="secondary voice-icon" aria-label="Record voice message"
      disabled={disabled} onClick={() => void start()}><Mic size={18} aria-hidden="true" /></button>}
    {phase && <>
      <span role="status">{phase === "recording" ? `Listening… ${seconds}s` : phase === "opening" ? "Opening microphone…" : "Transcribing audio…"}</span>
      {phase === "recording" && <button type="button" className="secondary voice-icon" aria-label="Stop recording" onClick={() => active.current?.stop()}><Square size={16} /></button>}
      <button type="button" className="secondary voice-icon" aria-label="Cancel voice input"
        onClick={() => { release(); setPhase(undefined); }}><X size={18} /></button>
    </>}
    {error && <span role="alert">{error}</span>}
  </div>;
}

export function SpokenResponse({ csrf, text }: { csrf: string; text: string }) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState("");
  const audio = useRef<HTMLAudioElement>(null);
  const request = useRef<AbortController>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  async function generate() {
    const controller = new AbortController();
    request.current = controller;
    setStatus("Generating speech…");
    try {
      const response = await rawRequest("/voice/synthesize", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ text }), signal: controller.signal,
      });
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      setUrl(URL.createObjectURL(blob));
      setStatus("Audio ready");
    } catch (error) { if (!controller.signal.aborted) setStatus(errorMessage(error)); }
  }

  if (!text.trim() || /\p{Script=Arabic}/u.test(text) || text.length > 1500) return null;
  return <div className="voice-controls">
    {!url && <button type="button" className="secondary voice-icon" aria-label="Generate spoken response"
      disabled={status === "Generating speech…"} onClick={() => void generate()}><Volume2 size={16} /></button>}
    {url && <>
      <audio ref={audio} src={url} controls aria-label="Spoken response"
        onPlay={() => setStatus("Speaking…")} onPause={() => setStatus("")} onEnded={() => setStatus("")} />
      <button type="button" className="secondary voice-icon" aria-label="Stop playback" onClick={() => {
        if (audio.current) { audio.current.pause(); audio.current.currentTime = 0; }
        setStatus("");
      }}><Square size={16} /></button>
    </>}
    <span role="status">{status}</span>
  </div>;
}
