/**
 * The product mark: a two-leaf sprout, taken from the supplied design.
 *
 * Solid rather than outlined, unlike the rest of the icon set — a logo is a
 * mark, not an icon, and the contrast is deliberate. It inherits
 * `currentColor`, so it is white on the forest sidebar and forest on the
 * ivory login card without needing two copies.
 *
 * The vein in the larger leaf is cut out rather than drawn on top, so it works
 * on any background: whatever is behind the mark shows through it. That is why
 * both leaves and the vein live in one path with `fill-rule="evenodd"`.
 */
export function Logo({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        fillRule="evenodd"
        clipRule="evenodd"
        d="
          M12.2 21.8
          C 17.6 19.3 21.1 13.2 20.6 5.2
          C 13.6 7.1 10.3 13.1 11.3 20.4
          L 12.2 21.8
          Z

          M11.0 21.6
          C 7.1 19.7 4.9 15.9 5.2 10.9
          C 9.0 12.9 11.2 16.7 10.8 20.9
          L 11.0 21.6
          Z

          M13.0 19.4
          C 14.0 15.1 15.9 11.6 18.6 9.0
          C 15.1 10.9 13.2 14.5 12.6 18.9
          Z
        "
      />
    </svg>
  )
}
