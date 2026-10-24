import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router'
import { useSession } from '../lib/session'
import { Icon, type IconName } from './Icon'
import { Logo } from './Logo'

export interface NavItem {
  to: string
  label: string
  icon: IconName
  count?: number
  end?: boolean
}

/**
 * The sidebar is built from the role's own items. A submitter is never handed
 * reviewer navigation and a reviewer never gets an upload action — the nav
 * cannot show a route the backend would refuse.
 *
 * Collapsing is a width change on wide screens. Below 760px the same element
 * becomes a drawer, because squeezing a sidebar, a list, a document and an
 * action panel into four narrow columns helps nobody.
 */
export function AppShell({
  nav,
  children,
  defaultCollapsed = false,
}: {
  nav: NavItem[]
  children: React.ReactNode
  /** Start as an icon rail. Used on the reviewer's detail page, where the
      document deserves the width more than the navigation does. */
  defaultCollapsed?: boolean
}) {
  const { state, signOut } = useSession()
  const identity = state.phase === 'signed-in' ? state.identity : null

  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const drawerRef = useRef<HTMLElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)

  // Escape closes the drawer and returns focus to the control that opened it,
  // so keyboard users are never stranded behind an overlay.
  useEffect(() => {
    if (!drawerOpen) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setDrawerOpen(false)
        menuButtonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  useEffect(() => {
    if (drawerOpen) drawerRef.current?.querySelector<HTMLElement>('a, button')?.focus()
  }, [drawerOpen])

  const initials = (identity?.display_name ?? '?')
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div className="shell">
      <header className="topbar">
        <button
          ref={menuButtonRef}
          type="button"
          className="btn btn--ghost btn--icon"
          style={{ color: 'inherit' }}
          aria-expanded={drawerOpen}
          aria-controls="app-nav"
          onClick={() => setDrawerOpen(true)}
        >
          <Icon name="menu" />
          <span className="sr-only">Open menu</span>
        </button>
        <span className="topbar__brand">Document Review</span>
      </header>

      {drawerOpen && (
        <button
          type="button"
          className="scrim"
          aria-label="Close menu"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      <nav
        id="app-nav"
        ref={drawerRef}
        className={[
          'sidebar',
          collapsed ? 'sidebar--collapsed' : '',
          drawerOpen ? 'sidebar--open' : '',
        ]
          .filter(Boolean)
          .join(' ')}
        aria-label="Main"
      >
        <div className="sidebar__brand">
          <Logo size={24} />
          <span className="sidebar__label">Document Review</span>
          <button
            type="button"
            className="sidebar__toggle"
            onClick={() => setCollapsed((value) => !value)}
            aria-pressed={collapsed}
          >
            <Icon name="panel-left" size={18} />
            <span className="sr-only">{collapsed ? 'Expand sidebar' : 'Collapse sidebar'}</span>
          </button>
        </div>

        <div className="nav">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'nav__item nav__item--active' : 'nav__item')}
              onClick={() => setDrawerOpen(false)}
              title={collapsed ? item.label : undefined}
            >
              <Icon name={item.icon} />
              <span className="sidebar__label">{item.label}</span>
              {typeof item.count === 'number' && (
                <span className="nav__count">
                  {item.count}
                  <span className="sr-only"> items</span>
                </span>
              )}
            </NavLink>
          ))}
        </div>

        <div className="sidebar__foot">
          {identity && (
            <div className="identity">
              <span className="identity__avatar" aria-hidden="true">
                {initials}
              </span>
              <span className="identity__text truncate">
                <span className="identity__name truncate">{identity.display_name}</span>
                <span className="identity__role small"> · {identity.role}</span>
              </span>
            </div>
          )}
          <button type="button" className="signout" onClick={() => void signOut()}>
            <Icon name="sign-out" size={18} />
            <span className="sidebar__label">Sign out</span>
          </button>
        </div>
      </nav>

      <main className="main">
        <div className="main__inner">{children}</div>
      </main>
    </div>
  )
}
