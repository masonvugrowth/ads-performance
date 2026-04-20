'use client'

import { describeRecType, describeSopReference } from '@/lib/recGlossary'

type TagKind = 'rec_type' | 'sop_reference'

interface InfoTagProps {
  code: string
  kind: TagKind
  // Applied to the outer pill wrapping code + info icon.
  className?: string
  // Optional — override the generated tooltip text.
  tooltip?: string
  // Tooltip heading label (e.g. "Playbook section"). Defaults based on kind.
  label?: string
  // Horizontal anchor of the tooltip. Defaults to 'left'.
  tooltipAlign?: 'left' | 'right'
}

export default function InfoTag({
  code,
  kind,
  className = '',
  tooltip,
  label,
  tooltipAlign = 'left',
}: InfoTagProps) {
  const description =
    tooltip ?? (kind === 'rec_type' ? describeRecType(code) : describeSopReference(code))

  const heading =
    label ?? (kind === 'rec_type' ? 'Recommendation code' : 'Playbook section')

  const tooltipPosition =
    tooltipAlign === 'right' ? 'right-0' : 'left-0'

  return (
    <span className={`group relative inline-flex items-center gap-1 ${className}`}>
      <span>{code}</span>
      <span
        tabIndex={0}
        aria-label={`What does ${code} mean?`}
        className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-gray-400 text-white text-[9px] font-bold font-sans not-italic leading-none cursor-help select-none focus:outline-none focus:ring-2 focus:ring-blue-400"
      >
        i
      </span>
      <span
        role="tooltip"
        className={`invisible opacity-0 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 transition-opacity duration-150 absolute bottom-full ${tooltipPosition} mb-2 z-50 w-72 rounded-md bg-gray-900 px-3 py-2 text-xs font-normal leading-snug text-gray-100 shadow-lg pointer-events-none whitespace-normal`}
      >
        <span className="block text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">
          {heading}
        </span>
        <span className="block font-mono text-[10px] text-gray-300 mb-1">
          {code}
        </span>
        {description}
      </span>
    </span>
  )
}
