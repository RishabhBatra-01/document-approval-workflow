/**
 * One outline icon family, drawn inline.
 *
 * All icons share a 24px grid, 1.6 stroke, round caps and joins, and inherit
 * `currentColor` — so they match whatever text they sit beside. Inlining them
 * avoids a webfont or sprite request, and means no icon ever renders as a
 * missing glyph.
 *
 * Icons are decorative here: every one sits next to a text label, so they are
 * hidden from assistive technology. Status is never conveyed by icon alone.
 */

export type IconName =
  | 'document'
  | 'inbox'
  | 'check-circle'
  | 'x-circle'
  | 'clock'
  | 'upload'
  | 'external'
  | 'refresh'
  | 'sign-out'
  | 'chevron-left'
  | 'menu'
  | 'panel-left'
  | 'close'
  | 'alert'
  | 'trash'
  | 'plus'

const PATHS: Record<IconName, React.ReactNode> = {
  document: (
    <>
      <path d="M14 3v4a1 1 0 0 0 1 1h4" />
      <path d="M19 8v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7Z" />
    </>
  ),
  inbox: (
    <>
      <path d="M4 13h4l1.5 2.5h5L16 13h4" />
      <path d="M5.5 5h13l1.5 8v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4l1.5-8Z" />
    </>
  ),
  'check-circle': (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.5 12.3 2.4 2.4 4.6-5" />
    </>
  ),
  'x-circle': (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m9.5 9.5 5 5M14.5 9.5l-5 5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.8V12l2.8 1.8" />
    </>
  ),
  upload: (
    <>
      <path d="M12 15V4" />
      <path d="m8 8 4-4 4 4" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </>
  ),
  external: (
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4 11 13" />
      <path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
    </>
  ),
  refresh: (
    <>
      <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" />
      <path d="M19.8 4.5V10h-5.5" />
    </>
  ),
  'sign-out': (
    <>
      <path d="M14 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="M10 8 6 12l4 4" />
      <path d="M6 12h9" />
    </>
  ),
  'chevron-left': <path d="m14 6-6 6 6 6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  'panel-left': (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M10 4.5v15" />
    </>
  ),
  close: <path d="M6 6l12 12M18 6 6 18" />,
  alert: (
    <>
      <path d="M12 8.5v4.2" />
      <path d="M12 16.3h.01" />
      <circle cx="12" cy="12" r="8.5" />
    </>
  ),
  trash: (
    <>
      <path d="M4.5 7h15" />
      <path d="M9.5 7V5.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V7" />
      <path d="M6.5 7l.8 11a2 2 0 0 0 2 1.9h5.4a2 2 0 0 0 2-1.9l.8-11" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
}

interface IconProps {
  name: IconName
  size?: number
  className?: string
}

export function Icon({ name, size = 20, className }: IconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  )
}
