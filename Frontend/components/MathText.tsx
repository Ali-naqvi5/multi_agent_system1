"use client";

import Latex from "react-latex-next";

interface Props {
  text: string;
  className?: string;
  block?: boolean;
}

/**
 * Renders text that may contain LaTeX delimiters:
 *   $...$ and \(...\)  — inline math
 *   $$...$$ and \[...\] — display math
 * Newlines are preserved as <br /> elements.
 */
export function MathText({ text, className, block = false }: Props) {
  if (!text) return null;
  const Tag = block ? "div" : "span";
  const lines = text.split("\n");
  return (
    <Tag className={className}>
      {lines.map((line, i) => (
        <span key={i}>
          <Latex>{line || " "}</Latex>
          {i < lines.length - 1 && <br />}
        </span>
      ))}
    </Tag>
  );
}
