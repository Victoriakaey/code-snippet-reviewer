import { useEffect, useMemo, useRef } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView, Decoration, gutter, GutterMarker } from "@codemirror/view";
import { RangeSetBuilder, type Extension } from "@codemirror/state";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { go } from "@codemirror/lang-go";

import type { Finding, Language, Severity } from "../types";

// --- language highlighting ------------------------------------------------------

function languageExtension(language: Language): Extension {
  switch (language) {
    case "python":
      return python();
    case "javascript":
      return javascript();
    case "typescript":
      return javascript({ typescript: true });
    case "java":
      return java();
    case "go":
      return go();
  }
}

// --- severity gutter markers ----------------------------------------------------

const SEVERITY_RANK: Record<Severity, number> = { critical: 3, warning: 2, info: 1 };
const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "var(--sev-critical)",
  warning: "var(--sev-warning)",
  info: "var(--sev-info)",
};

/** Highest severity per line covered by any finding (line_start..line_end inclusive). */
function lineSeverityMap(findings: Finding[]): Map<number, Severity> {
  const map = new Map<number, Severity>();
  for (const f of findings) {
    for (let n = f.line_start; n <= f.line_end; n++) {
      const cur = map.get(n);
      if (!cur || SEVERITY_RANK[f.severity] > SEVERITY_RANK[cur]) map.set(n, f.severity);
    }
  }
  return map;
}

class SeverityMarker extends GutterMarker {
  constructor(private readonly severity: Severity) {
    super();
  }
  toDOM() {
    const el = document.createElement("div");
    el.className = "cm-sev-dot";
    el.style.background = SEVERITY_COLOR[this.severity];
    el.title = `${this.severity} finding on this line`;
    return el;
  }
}

function severityGutter(
  lineSev: Map<number, Severity>,
  onLineClick: (line: number) => void,
): Extension {
  return gutter({
    class: "cm-sev-gutter",
    lineMarker(view, block) {
      const n = view.state.doc.lineAt(block.from).number;
      const sev = lineSev.get(n);
      return sev ? new SeverityMarker(sev) : null;
    },
    domEventHandlers: {
      mousedown(view, block) {
        const n = view.state.doc.lineAt(block.from).number;
        if (lineSev.has(n)) {
          onLineClick(n);
          return true;
        }
        return false;
      },
    },
  });
}

// --- selected-finding line highlight (distinct from severity markers) -----------

function selectedHighlight(range: { start: number; end: number } | null): Extension {
  return EditorView.decorations.of((view) => {
    if (!range) return Decoration.none;
    const builder = new RangeSetBuilder<Decoration>();
    for (let n = range.start; n <= range.end; n++) {
      if (n < 1 || n > view.state.doc.lines) continue;
      const line = view.state.doc.line(n);
      builder.add(
        line.from,
        line.from,
        Decoration.line({ attributes: { class: "cm-selected-finding" } }),
      );
    }
    return builder.finish();
  });
}

// --- component ------------------------------------------------------------------

interface CodeEditorProps {
  value: string;
  language: Language;
  editable: boolean;
  onChange?: (value: string) => void;
  findings?: Finding[];
  selectedRange?: { start: number; end: number } | null;
  onLineClick?: (line: number) => void;
  minHeight?: string;
  /** When set (e.g. "100%"), the editor fills its container instead of growing with content. */
  height?: string;
}

export function CodeEditor({
  value,
  language,
  editable,
  onChange,
  findings,
  selectedRange = null,
  onLineClick,
  minHeight = "240px",
  height,
}: CodeEditorProps) {
  const viewRef = useRef<EditorView | null>(null);

  const extensions = useMemo(() => {
    const exts: Extension[] = [languageExtension(language), EditorView.lineWrapping];
    if (findings && findings.length > 0) {
      exts.push(severityGutter(lineSeverityMap(findings), (n) => onLineClick?.(n)));
    }
    exts.push(selectedHighlight(selectedRange));
    return exts;
  }, [language, findings, selectedRange, onLineClick]);

  // Scroll the selected range into view when it changes.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || !selectedRange) return;
    const total = view.state.doc.lines;
    const line = Math.min(Math.max(selectedRange.start, 1), total);
    const pos = view.state.doc.line(line).from;
    view.dispatch({ effects: EditorView.scrollIntoView(pos, { y: "center" }) });
  }, [selectedRange]);

  return (
    <CodeMirror
      value={value}
      editable={editable}
      readOnly={!editable}
      extensions={extensions}
      onChange={onChange}
      onCreateEditor={(view) => (viewRef.current = view)}
      basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: editable }}
      minHeight={height ? undefined : minHeight}
      height={height}
      style={height ? { height: "100%" } : undefined}
      theme="light"
    />
  );
}
