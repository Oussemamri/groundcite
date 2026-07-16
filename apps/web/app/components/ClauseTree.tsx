"use client";

import { useEffect, useMemo, useState } from "react";
import type { SectionOut } from "@/lib/api";

interface TreeNode extends SectionOut {
  children: TreeNode[];
}

function buildTree(sections: SectionOut[]): TreeNode[] {
  const byId = new Map<string, TreeNode>();
  for (const s of sections) byId.set(s.id, { ...s, children: [] });
  const roots: TreeNode[] = [];
  for (const s of sections) {
    const node = byId.get(s.id)!;
    const parent = s.parent_id ? byId.get(s.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const byOrdinal = (a: TreeNode, b: TreeNode) => a.ordinal - b.ordinal;
  for (const node of byId.values()) node.children.sort(byOrdinal);
  roots.sort(byOrdinal);
  return roots;
}

function ancestorIds(sections: SectionOut[], targetId: string | null): string[] {
  if (!targetId) return [];
  const byId = new Map(sections.map((s) => [s.id, s]));
  const ancestors: string[] = [];
  let cur = byId.get(targetId)?.parent_id ?? null;
  while (cur) {
    ancestors.push(cur);
    cur = byId.get(cur)?.parent_id ?? null;
  }
  return ancestors;
}

/**
 * Recursive clause hierarchy (spec §10 reader, AD-10). Far-25 has 23 root
 * subparts/appendices and depth to level 6 (verified against the live
 * corpus) -- collapsed by default so the tree opens as a 23-item list, not
 * a 3,291-row wall of text. The active chunk's ancestor chain auto-expands
 * so a citation deep-link lands somewhere visible without a manual hunt.
 */
export function ClauseTree({
  sections,
  activeSectionId,
  onSelect,
}: {
  sections: SectionOut[];
  activeSectionId: string | null;
  onSelect: (sectionId: string) => void;
}) {
  const tree = useMemo(() => buildTree(sections), [sections]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!activeSectionId) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const id of ancestorIds(sections, activeSectionId)) next.add(id);
      return next;
    });
  }, [activeSectionId, sections]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function renderNode(node: TreeNode, depth: number) {
    const isOpen = expanded.has(node.id);
    const isActive = node.id === activeSectionId;
    const hasChildren = node.children.length > 0;
    return (
      <li key={node.id}>
        <div
          className={
            "flex items-center gap-1.5 rounded px-1.5 py-1 text-xs " +
            (isActive ? "bg-link/10 text-link" : "text-text/70 hover:text-text")
          }
          style={{ paddingLeft: `${depth * 14 + 4}px` }}
        >
          {hasChildren ? (
            <button
              type="button"
              onClick={() => toggle(node.id)}
              aria-expanded={isOpen}
              aria-label={isOpen ? `Collapse ${node.clause_id}` : `Expand ${node.clause_id}`}
              className="w-3 shrink-0 text-center text-text/40 hover:text-text"
            >
              {isOpen ? "−" : "+"}
            </button>
          ) : (
            <span aria-hidden className="w-3 shrink-0" />
          )}
          <button
            type="button"
            onClick={() => onSelect(node.id)}
            aria-current={isActive ? "true" : undefined}
            className="min-w-0 flex-1 truncate text-left"
          >
            <span className="clause-id mr-1.5">{node.clause_id}</span>
            {node.title && <span className="text-text/50">{node.title}</span>}
          </button>
        </div>
        {hasChildren && isOpen && <ul>{node.children.map((child) => renderNode(child, depth + 1))}</ul>}
      </li>
    );
  }

  if (sections.length === 0) {
    return <p className="text-sm text-text/40">No sections.</p>;
  }

  return <ul className="flex flex-col">{tree.map((node) => renderNode(node, 0))}</ul>;
}
