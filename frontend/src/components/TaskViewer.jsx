import { Component, Suspense, useEffect, useMemo } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { Center, OrbitControls, useGLTF } from "@react-three/drei";
import { DoubleSide, MeshStandardMaterial } from "three";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";

function Model({ url }) {
  const { scene } = useGLTF(url);
  const preparedScene = useMemo(() => {
    const cloned = scene.clone(true);
    cloned.traverse((object) => {
      if (!object.isMesh) {
        return;
      }
      if (!object.geometry.getAttribute("normal")) {
        object.geometry.computeVertexNormals();
      }
      if (object.geometry.getAttribute("color")) {
        object.material = new MeshStandardMaterial({
          vertexColors: true,
          metalness: 0,
          roughness: 0.72,
          side: DoubleSide,
        });
        return;
      }
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      const clonedMaterials = materials.map((material) => {
        const next = material.clone();
        next.side = DoubleSide;
        if ("metalness" in next) {
          next.metalness = 0;
        }
        if ("roughness" in next) {
          next.roughness = Math.max(next.roughness ?? 0, 0.55);
        }
        return next;
      });
      object.material = Array.isArray(object.material) ? clonedMaterials : clonedMaterials[0];
    });
    return cloned;
  }, [scene]);

  useEffect(() => {
    return () => {
      preparedScene.traverse((object) => {
        if (!object.isMesh) {
          return;
        }
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((material) => material?.dispose?.());
      });
    };
  }, [preparedScene]);

  return (
    <Center>
      <primitive object={preparedScene} />
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
          <hemisphereLight args={["#ffffff", "#cbd5e1", 1.1]} />
          <ambientLight intensity={0.95} />
          <directionalLight position={[3, 4, 5]} intensity={1.5} />
          <Suspense fallback={null}>
            {outputType === "ply" ? <PlyPointCloud url={outputUrl} /> : <Model url={outputUrl} />}
          </Suspense>
          <OrbitControls enableDamping />
        </Canvas>
      </div>
    </ViewerErrorBoundary>
  );
}
