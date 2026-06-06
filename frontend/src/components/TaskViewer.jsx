import { Component, Suspense, useEffect, useMemo } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { Center, OrbitControls, useGLTF } from "@react-three/drei";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";

function Model({ url }) {
  const { scene } = useGLTF(url);
  return (
    <Center>
      <primitive object={scene} />
    </Center>
  );
}

function PlyPointCloud({ url }) {
  const loadedGeometry = useLoader(PLYLoader, url);
  const geometry = useMemo(() => {
    const cloned = loadedGeometry.clone();
    cloned.computeBoundingSphere();
    return cloned;
  }, [loadedGeometry]);

  useEffect(() => {
    return () => geometry.dispose();
  }, [geometry]);

  return (
    <Center>
      <points geometry={geometry}>
        <pointsMaterial
          attach="material"
          size={0.012}
          sizeAttenuation
          vertexColors={Boolean(geometry.getAttribute("color"))}
        />
      </points>
    </Center>
  );
}

class ViewerErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failedKey: null };
  }

  static getDerivedStateFromError() {
    return { failedKey: "failed" };
  }

  componentDidUpdate(previousProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.failedKey) {
      this.setState({ failedKey: null });
    }
  }

  render() {
    if (this.state.failedKey) {
      return <div className="placeholder">Preview failed. Download the output to inspect it.</div>;
    }
    return this.props.children;
  }
}

export default function TaskViewer({ outputUrl, output }) {
  if (!outputUrl) {
    return <div className="placeholder">No previewable output yet</div>;
  }

  const outputType = output?.type;

  return (
    <ViewerErrorBoundary resetKey={outputUrl}>
      <div className="canvas-wrap">
        <Canvas camera={{ position: [0, 0, 3], fov: 45 }}>
          <color attach="background" args={["#eef2f7"]} />
          <ambientLight intensity={0.8} />
          <directionalLight position={[3, 3, 3]} intensity={1.2} />
          <Suspense fallback={null}>
            {outputType === "ply" ? <PlyPointCloud url={outputUrl} /> : <Model url={outputUrl} />}
          </Suspense>
          <OrbitControls enableDamping />
        </Canvas>
      </div>
    </ViewerErrorBoundary>
  );
}
