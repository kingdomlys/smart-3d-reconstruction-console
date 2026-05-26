import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";

function Model({ url }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

export default function TaskViewer({ outputUrl, outputPath }) {
  if (!outputUrl) {
    return <div className="placeholder">No output yet</div>;
  }
  if (outputPath && outputPath.endsWith(".ply")) {
    return (
      <div className="placeholder">
        3DGS output detected. Viewer support will be added next.
      </div>
    );
  }

  return (
    <div className="canvas-wrap">
      <Canvas camera={{ position: [0, 0, 3], fov: 45 }}>
        <ambientLight intensity={0.8} />
        <directionalLight position={[3, 3, 3]} intensity={1.2} />
        <Suspense fallback={null}>
          <Model url={outputUrl} />
        </Suspense>
        <OrbitControls enableDamping />
      </Canvas>
    </div>
  );
}
