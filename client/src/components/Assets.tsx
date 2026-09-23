import { useState } from "react";

import { api } from "../lib/api";
import { fileSize } from "../lib/format";
import type { AssetMeta } from "../lib/types";
import { useToast } from "./ui";

export function svgSrc(content: string): string {
  // An <img> never executes scripts inside an SVG, so generated drawings stay inert.
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(content)}`;
}

export function Figures({ assets }: { assets: AssetMeta[] }) {
  return (
    <>
      {assets
        .filter((a) => a.kind === "svg" && a.content)
        .map((a) => (
          <img key={a.name} src={svgSrc(a.content ?? "")} alt={`Рисунок ${a.name}`} className="figure" />
        ))}
    </>
  );
}

function label(asset: AssetMeta): string {
  if (asset.deferred) return "≈ 1 000 000 чисел";
  return fileSize(asset.size);
}

export async function downloadAsset(instanceId: number, name: string): Promise<Blob> {
  return api.blob(`/instances/${instanceId}/assets/${encodeURIComponent(name)}`);
}

export function FileChips({ instanceId, assets }: { instanceId: number; assets: AssetMeta[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast((s) => s.show);
  const files = assets.filter((a) => a.kind !== "svg");
  if (!files.length) return null;
  const save = async (asset: AssetMeta) => {
    setBusy(asset.name);
    try {
      const blob = await downloadAsset(instanceId, asset.name);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = asset.name;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch {
      toast("Не удалось скачать файл", "bad");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="chips">
      {files.map((asset) => (
        <button key={asset.name} className="file-chip" onClick={() => void save(asset)} disabled={busy === asset.name}>
          📄 {asset.name} · {label(asset)} · {busy === asset.name ? "…" : "скачать"}
        </button>
      ))}
    </div>
  );
}
