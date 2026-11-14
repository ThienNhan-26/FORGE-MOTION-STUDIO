import { Canvas } from '@react-three/fiber';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SceneWorld } from '../shared/SceneWorld';
import { OBJECT_PRESETS, type ObjectKind, type Scene3DSpec, type SceneObjectSpec, type Vec3 } from '../shared/sceneTypes';

type Job = { job_id: string; status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'; output?: string; error?: string; evidence?: string };

const API = '/api';
const OBJECTS: { kind: ObjectKind; label: string; icon: string }[] = [
  { kind: 'pine', label: 'Cây thông', icon: '♠' }, { kind: 'tree', label: 'Cây', icon: '♣' },
  { kind: 'house', label: 'Nhà', icon: '⌂' }, { kind: 'cloud', label: 'Mây', icon: '☁' },
  { kind: 'rock', label: 'Đá', icon: '◆' }, { kind: 'crystal', label: 'Pha lê', icon: '◇' },
  { kind: 'cube', label: 'Khối lập phương', icon: '▣' }, { kind: 'sphere', label: 'Khối cầu', icon: '●' },
];

function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T; }

function VecEditor({ label, value, onChange, step = 0.1 }: { label: string; value: Vec3; onChange: (v: Vec3) => void; step?: number }) {
  const axis = ['X', 'Y', 'Z'];
  return <div className="vec-editor"><div className="field-label">{label}</div><div className="vec-inputs">{value.map((n, i) => (
    <label key={axis[i]} className={`axis axis-${axis[i].toLowerCase()}`}><span>{axis[i]}</span>
      <input type="number" step={step} value={Number(n.toFixed(3))} onChange={(e) => {
        const next: Vec3 = [...value]; next[i] = Number(e.target.value); onChange(next);
      }} />
    </label>
  ))}</div></div>;
}

export default function App() {
  const [scene, setScene] = useState<Scene3DSpec | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>('island-body');
  const [frame, setFrame] = useState(0);
  const [viewResetToken, setViewResetToken] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [toast, setToast] = useState('');
  const [activeTab, setActiveTab] = useState<'object' | 'scene'>('object');
  const [renderStatus, setRenderStatus] = useState('READY');

  const totalFrames = scene ? scene.duration_seconds * scene.fps : 540;
  const selected = useMemo(() => scene?.objects.find((item) => item.id === selectedId) ?? null, [scene, selectedId]);

  useEffect(() => {
    let active = true;
    fetch(`${API}/scene?project_id=floating-island`).then(async (r) => {
      if (!r.ok) throw new Error(await r.text());
      return r.json() as Promise<Scene3DSpec>;
    }).then((data) => { if (active) setScene(data); }).catch((error) => {
      if (active) setToast(`Không kết nối được FORGE: ${error.message}`);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(''), 4200);
    return () => window.clearTimeout(id);
  }, [toast]);

  useEffect(() => {
    if (!playing || !scene) return;
    const timer = window.setInterval(() => setFrame((current) => Math.min(totalFrames - 1, current + 1)), 1000 / scene.fps);
    return () => window.clearInterval(timer);
  }, [playing, scene, totalFrames]);

  useEffect(() => {
    if (playing && frame >= totalFrames - 1) {
      setPlaying(false);
      setFrame(0);
    }
  }, [frame, playing, totalFrames]);

  useEffect(() => {
    if (!job || !['QUEUED', 'RUNNING'].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API}/jobs/${job.job_id}`);
        if (!response.ok) return;
        const next = await response.json() as Job;
        setJob(next);
        if (next.status === 'COMPLETED') {
          setBusy(false); setRenderStatus('RENDER COMPLETE');
          setToast(`Đã xuất video: ${next.evidence ?? next.output ?? 'MP4'}`);
        } else if (next.status === 'FAILED') {
          setBusy(false); setRenderStatus('RENDER FAILED'); setToast(next.error ?? 'Render thất bại.');
        }
      } catch { /* next poll will retry */ }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job]);

  const updateScene = useCallback((updater: (current: Scene3DSpec) => Scene3DSpec) => {
    setScene((current) => current ? updater(current) : current);
    setDirty(true);
  }, []);

  const updateObject = useCallback((id: string, patch: Partial<SceneObjectSpec>) => {
    updateScene((current) => ({ ...current, objects: current.objects.map((item) => item.id === id ? { ...item, ...patch } : item) }));
  }, [updateScene]);

  const saveScene = async () => {
    if (!scene || busy) return;
    setBusy(true);
    try {
      const response = await fetch(`${API}/scene`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scene) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Không thể lưu scene.');
      setDirty(false); setToast(`Đã lưu scene · ${result.path ?? scene.project_id}`);
    } catch (error) { setToast(`Lưu thất bại: ${String(error)}`); }
    finally { setBusy(false); }
  };

  const renderVideo = async () => {
    if (!scene || busy) return;
    setBusy(true); setRenderStatus('SUBMITTING'); setPlaying(false);
    try {
      const response = await fetch(`${API}/render`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scene) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Không thể gửi lệnh render.');
      setDirty(false); setJob(result as Job); setRenderStatus('RENDERING'); setToast('Đã gửi scene sang Remotion render.');
    } catch (error) { setBusy(false); setRenderStatus('RENDER FAILED'); setToast(`Render thất bại: ${String(error)}`); }
  };

  const addObject = (kind: ObjectKind) => {
    if (!scene) return;
    const id = `${kind}-${Date.now().toString(36)}`;
    const preset = clone(OBJECT_PRESETS[kind]);
    const offset = scene.objects.filter((item) => item.kind === kind).length;
    preset.position = [preset.position[0] + offset * 0.28, preset.position[1], preset.position[2] + offset * 0.24];
    updateScene((current) => ({ ...current, objects: [...current.objects, { ...preset, id }] }));
    setSelectedId(id); setActiveTab('object'); setToast(`Đã thêm ${preset.name}`);
  };

  const deleteSelected = () => {
    if (!scene || !selected) return;
    if (selected.kind === 'island') { setToast('Không thể xóa khối đảo nền.'); return; }
    updateScene((current) => ({ ...current, objects: current.objects.filter((item) => item.id !== selected.id) }));
    setSelectedId(null);
  };

  const resetCamera = () => { setFrame(0); setPlaying(false); setViewResetToken((value) => value + 1); setToast('Đã đưa camera về frame đầu.'); };
  const formatTime = (f: number) => `${Math.floor(f / (scene?.fps ?? 30) / 60).toString().padStart(2, '0')}:${(Math.floor(f / (scene?.fps ?? 30)) % 60).toString().padStart(2, '0')}:${(f % (scene?.fps ?? 30)).toString().padStart(2, '0')}`;

  if (!scene) return <div className="loading-screen"><div className="brand-mark">F</div><h2>FORGE MOTION STUDIO</h2><p>Đang kết nối local scene server…</p><span className="loading-line" /></div>;

  return (
    <div className="studio-shell">
      <header className="topbar">
        <div className="brand"><div className="brand-mark">F</div><div><strong>FORGE</strong><span>MOTION STUDIO</span></div></div>
        <div className="project-title"><span className="crumb">PROJECT /</span><input value={scene.title} onChange={(e) => updateScene((current) => ({ ...current, title: e.target.value }))} aria-label="Tên dự án" /><span className={`dirty-dot ${dirty ? 'is-dirty' : ''}`} title={dirty ? 'Chưa lưu' : 'Đã lưu'} /></div>
        <div className="top-actions"><span className="system-pill"><i /> LOCAL RUNTIME</span><button className="btn btn-ghost" onClick={saveScene} disabled={busy}>{busy ? 'ĐANG XỬ LÝ…' : 'LƯU SCENE'}</button><button className="btn btn-primary" onClick={renderVideo} disabled={busy}>▶  RENDER MP4</button></div>
      </header>

      <div className="workspace-grid">
        <aside className="left-panel panel">
          <div className="panel-heading"><div><span className="eyebrow">SCENE GRAPH</span><h3>Phân cấp cảnh</h3></div><span className="count-badge">{scene.objects.length}</span></div>
          <div className="hierarchy-list">
            <button className="hierarchy-root" onClick={() => setSelectedId(null)}><span className="tree-chevron">⌄</span><span className="object-glyph world">◎</span><span>World Scene</span></button>
            {scene.objects.map((object) => (
              <button key={object.id} className={`hierarchy-item ${selectedId === object.id ? 'selected' : ''}`} onClick={() => { setSelectedId(object.id); setActiveTab('object'); }}>
                <span className="tree-branch">└</span><span className={`object-glyph ${object.kind}`}>{object.kind === 'pine' || object.kind === 'tree' ? '♠' : object.kind === 'house' ? '⌂' : object.kind === 'cloud' ? '☁' : object.kind === 'island' ? '◈' : '◆'}</span><span className="object-name">{object.name}</span><span className={`visibility ${object.visible ? '' : 'hidden'}`}>{object.visible ? '◉' : '○'}</span>
              </button>
            ))}
          </div>
          <div className="panel-divider" />
          <div className="panel-heading compact"><div><span className="eyebrow">ADD TO SCENE</span><h3>Thư viện đối tượng</h3></div></div>
          <div className="asset-grid">{OBJECTS.map((item) => <button key={item.kind} onClick={() => addObject(item.kind)} className="asset-button"><span>{item.icon}</span><small>{item.label}</small></button>)}</div>
          <div className="left-footer"><span className="online-dot" /> Scene data local · JSON contract v1</div>
        </aside>

        <main className="center-column">
          <div className="viewport-toolbar"><div className="viewport-label"><span className="live-dot" /> VIEWPORT <span className="subtle">· PERSPECTIVE</span></div><div className="viewport-tools"><span>1920 × 1080</span><span className="tool-divider" /><span>{scene.style.toUpperCase().replace('_', ' ')}</span><span className="tool-divider" /><button onClick={resetCamera}>⌖ RESET VIEW</button></div></div>
          <div className="viewport-wrap">
            <Canvas shadows dpr={[1, 1.75]} camera={{ position: scene.camera.position, fov: scene.camera.fov }} onPointerMissed={() => setSelectedId(null)}>
              <SceneWorld scene={scene} frame={frame} interactive resetToken={viewResetToken} selectedObjectId={selectedId} onObjectSelect={setSelectedId} />
            </Canvas>
            <div className="viewport-overlay top-left"><span className="overlay-chip">3D PREVIEW</span><span className="overlay-chip muted">FRAME {frame.toString().padStart(3, '0')}</span></div>
            <div className="viewport-overlay bottom-left"><span>DRAG · ORBIT</span><span>SCROLL · ZOOM</span><span>CLICK · SELECT</span></div>
            <div className="viewport-overlay bottom-right"><span className="axis-widget"><b>X</b><i /><b>Y</b><i /><b>Z</b></span></div>
          </div>
          <section className="timeline-panel panel">
            <div className="timeline-header"><div><span className="eyebrow">ANIMATION</span><h3>Timeline</h3></div><div className="timeline-meta"><span>{scene.fps} FPS</span><span>{scene.duration_seconds.toFixed(1)} SEC</span><strong>{formatTime(frame)}</strong></div></div>
            <div className="transport-row"><div className="transport-controls"><button onClick={() => { setPlaying(false); setFrame(0); }} title="Về đầu">|◀</button><button className="play-button" onClick={() => { if (!playing && frame >= totalFrames - 1) setFrame(0); setPlaying((v) => !v); }} title={playing ? 'Tạm dừng' : 'Phát'}>{playing ? 'Ⅱ' : '▶'}</button><button onClick={() => { setPlaying(false); setFrame(totalFrames - 1); }} title="Tới cuối">▶|</button></div><div className="frame-readout">{formatTime(frame)} <span>/</span> {formatTime(totalFrames - 1)}</div></div>
            <input className="timeline-scrubber" type="range" min={0} max={Math.max(1, totalFrames - 1)} value={Math.min(frame, totalFrames - 1)} onChange={(e) => { setPlaying(false); setFrame(Number(e.target.value)); }} />
            <div className="timeline-ruler"><span>00:00</span><span>00:04</span><span>00:08</span><span>00:12</span><span>00:16</span><span>{scene.duration_seconds}s</span></div>
            <div className="timeline-tracks"><div className="track-label">CAMERA</div><div className="track-bar camera-track"><span className="track-clip">{scene.camera.motion.toUpperCase()} · CAMERA PATH</span><i className="playhead" style={{ left: `${(frame / Math.max(1, totalFrames - 1)) * 100}%` }} /></div></div>
            <div className="timeline-tracks object-track-row"><div className="track-label">OBJECTS</div><div className="track-bar object-tracks">{scene.objects.slice(0, 6).map((object, index) => <span key={object.id} className={`mini-clip clip-${index % 6}`} style={{ width: `${Math.max(7, 100 - index * 3)}%` }} title={object.name}>{object.name}</span>)}<i className="playhead" style={{ left: `${(frame / Math.max(1, totalFrames - 1)) * 100}%` }} /></div></div>
          </section>
          <footer className="statusbar"><span><i className="online-dot" /> READY</span><span>SCENE OBJECTS: {scene.objects.length}</span><span>SELECTED: {selected?.name ?? 'NONE'}</span><span className="render-indicator">{renderStatus}</span></footer>
        </main>

        <aside className="right-panel panel">
          <div className="inspector-tabs"><button className={activeTab === 'object' ? 'active' : ''} onClick={() => setActiveTab('object')}>INSPECTOR</button><button className={activeTab === 'scene' ? 'active' : ''} onClick={() => setActiveTab('scene')}>SCENE</button></div>
          {activeTab === 'object' ? (
            selected ? <>
              <div className="inspector-title"><div className="inspector-icon">{selected.kind === 'house' ? '⌂' : selected.kind === 'cloud' ? '☁' : '◈'}</div><div><span className="eyebrow">OBJECT / {selected.kind.toUpperCase()}</span><h3>{selected.name}</h3></div></div>
              <div className="inspector-section"><div className="section-head"><h4>TRANSFORM</h4><button onClick={() => updateObject(selected.id, { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] })}>RESET</button></div>
                <VecEditor label="Position" value={selected.position} onChange={(v) => updateObject(selected.id, { position: v })} />
                <VecEditor label="Rotation" value={selected.rotation.map((v) => Number((v * 180 / Math.PI).toFixed(2))) as Vec3} step={1} onChange={(v) => updateObject(selected.id, { rotation: v.map((n) => n * Math.PI / 180) as Vec3 })} />
                <VecEditor label="Scale" value={selected.scale} onChange={(v) => updateObject(selected.id, { scale: v.map((n) => Math.max(0.01, n)) as Vec3 })} />
              </div>
              <div className="inspector-section"><div className="section-head"><h4>APPEARANCE</h4></div><div className="color-row"><label>Base Color</label><input type="color" value={selected.color} onChange={(e) => updateObject(selected.id, { color: e.target.value })} /><code>{selected.color.toUpperCase()}</code></div>
                <label className="select-row"><span>Animation</span><select value={selected.animation} onChange={(e) => updateObject(selected.id, { animation: e.target.value as SceneObjectSpec['animation'] })}><option value="none">None</option><option value="float">Float</option><option value="rotate">Rotate</option><option value="pulse">Pulse</option></select></label>
                <label className="toggle-row"><span>Visible in render</span><input type="checkbox" checked={selected.visible} onChange={(e) => updateObject(selected.id, { visible: e.target.checked })} /></label>
              </div>
              <div className="inspector-actions"><button className="btn btn-danger" onClick={deleteSelected} disabled={selected.kind === 'island'}>DELETE OBJECT</button></div>
            </> : <div className="empty-inspector"><div>◎</div><h3>Chọn một đối tượng</h3><p>Chọn object trong Scene Graph hoặc nhấp trực tiếp lên mô hình 3D để chỉnh sửa transform, vật liệu và animation.</p></div>
          ) : (
            <>
              <div className="inspector-title"><div className="inspector-icon">◉</div><div><span className="eyebrow">GLOBAL SETTINGS</span><h3>Scene Settings</h3></div></div>
              <div className="inspector-section"><div className="section-head"><h4>OUTPUT</h4></div>
                <div className="select-row"><span>Visual Style</span><span className="style-chip">LOW POLY · G1</span></div>
                <label className="select-row"><span>Duration (seconds)</span><input type="number" min={3} max={120} value={scene.duration_seconds} onChange={(e) => updateScene((s) => ({ ...s, duration_seconds: Math.max(3, Math.min(120, Number(e.target.value))) }))} /></label>
                <label className="select-row"><span>Frame Rate</span><select value={scene.fps} onChange={(e) => updateScene((s) => ({ ...s, fps: Number(e.target.value) }))}><option value={24}>24 FPS</option><option value={30}>30 FPS</option><option value={60}>60 FPS</option></select></label>
              </div>
              <div className="inspector-section"><div className="section-head"><h4>CAMERA</h4></div>
                <label className="select-row"><span>Camera Motion</span><select value={scene.camera.motion} onChange={(e) => updateScene((s) => ({ ...s, camera: { ...s.camera, motion: e.target.value as Scene3DSpec['camera']['motion'] } }))}><option value="none">Static</option><option value="push_in">Push In</option><option value="orbit">Orbit</option></select></label>
                <VecEditor label="Start Position" value={scene.camera.position} onChange={(v) => updateScene((s) => ({ ...s, camera: { ...s.camera, position: v } }))} />
                <VecEditor label="End Position" value={scene.camera.end_position} onChange={(v) => updateScene((s) => ({ ...s, camera: { ...s.camera, end_position: v } }))} />
                <label className="select-row"><span>Field of View</span><input type="number" min={20} max={100} value={scene.camera.fov} onChange={(e) => updateScene((s) => ({ ...s, camera: { ...s.camera, fov: Math.max(20, Math.min(100, Number(e.target.value))) } }))} /></label>
              </div>
              <div className="inspector-section"><div className="section-head"><h4>ENVIRONMENT</h4></div>
                <div className="color-row"><label>Background</label><input type="color" value={scene.environment.background} onChange={(e) => updateScene((s) => ({ ...s, environment: { ...s.environment, background: e.target.value, fog_color: e.target.value } }))} /><code>{scene.environment.background.toUpperCase()}</code></div>
                <label className="range-row"><span>Ambient Light <b>{scene.environment.ambient_intensity.toFixed(2)}</b></span><input type="range" min={0} max={3} step={0.05} value={scene.environment.ambient_intensity} onChange={(e) => updateScene((s) => ({ ...s, environment: { ...s.environment, ambient_intensity: Number(e.target.value) } }))} /></label>
              </div>
            </>
          )}
        </aside>
      </div>
      {toast && <div className="toast">{toast}</div>}
      {job?.status === 'COMPLETED' && job.evidence && <div className="render-result"><span>MP4 READY</span><code>{job.evidence}</code><button onClick={() => setJob(null)}>×</button></div>}
    </div>
  );
}
