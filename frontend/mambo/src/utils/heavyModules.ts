/**
 * Lazy loaders for heavy chat-rendering dependencies (mermaid / highlight.js).
 *
 * These libraries used to be statically imported by CodeBlock.vue, which pulled
 * them into the initial route chunk (~1MB). They are now loaded on demand via
 * dynamic import(), with an idle-time warm-up so the first code block / diagram
 * renders without a visible load delay.
 *
 * The per-module promise is cached: a warm-up call and an on-demand call share
 * the same in-flight import, so there is never a double load or a race.
 */

let hljsPromise: Promise<typeof import('highlight.js')> | null = null
export function loadHighlightJs(): Promise<typeof import('highlight.js')> {
  if (!hljsPromise) hljsPromise = import('highlight.js')
  return hljsPromise
}

let mermaidPromise: Promise<typeof import('mermaid')> | null = null
export function loadMermaid(): Promise<typeof import('mermaid')> {
  if (!mermaidPromise) mermaidPromise = import('mermaid')
  return mermaidPromise
}

/**
 * Warm up the heavy modules during browser idle time (after first paint),
 * so they are ready before the user actually encounters a code block.
 * Components awaiting loadHighlightJs()/loadMermaid() share the same promise,
 * so calling both paths is safe.
 */
export function warmUpHeavyModules(): void {
  const warm = () => {
    loadHighlightJs().catch(() => {})
    loadMermaid().catch(() => {})
  }
  if ('requestIdleCallback' in window) {
    ;(window as unknown as { requestIdleCallback: (cb: () => void, opts?: { timeout: number }) => void }).requestIdleCallback(warm, { timeout: 3000 })
  } else {
    setTimeout(warm, 2000)
  }
}
