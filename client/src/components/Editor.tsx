// CodeMirror 6 with Python highlighting. Loaded lazily: it lives in its own chunk.
import { python } from "@codemirror/lang-python";
import { EditorView, basicSetup } from "codemirror";
import { useEffect, useRef } from "react";

export default function Editor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const changed = useRef(onChange);
  changed.current = onChange;
  useEffect(() => {
    if (!host.current) return;
    view.current = new EditorView({
      doc: value,
      parent: host.current,
      extensions: [
        basicSetup,
        python(),
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) changed.current(update.state.doc.toString());
        }),
      ],
    });
    return () => view.current?.destroy();
    // The document is owned by CodeMirror after mount; `value` only seeds it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const current = view.current;
    if (current && current.state.doc.toString() !== value) {
      current.dispatch({ changes: { from: 0, to: current.state.doc.length, insert: value } });
    }
  }, [value]);
  return <div ref={host} className="editor" />;
}
