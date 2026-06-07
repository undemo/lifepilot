"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { CalendarClock, Home, Route, Settings, UserRound } from "lucide-react";
import { usePathname } from "next/navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [lastPlanHref, setLastPlanHref] = useState("/plans");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const created = window.sessionStorage.getItem("lifepilot_last_create");
      const parsed = created ? (JSON.parse(created) as { plan_id?: string }) : null;
      if (parsed?.plan_id) setLastPlanHref(`/plans/${parsed.plan_id}`);
    } catch {
      setLastPlanHref("/plans");
    } finally {
      setHydrated(true);
    }
  }, []);

  const navItems = [
    { href: "/", label: "首页", icon: Home, active: pathname === "/" },
    { href: "/plans", label: "计划", icon: CalendarClock, active: pathname === "/plans" },
    { href: lastPlanHref, label: "时间轴", icon: Route, active: pathname.startsWith("/plans/") || pathname.startsWith("/execution") || pathname.startsWith("/feedback") },
    { href: "/memory", label: "我的", icon: UserRound, active: pathname.startsWith("/memory") || pathname.startsWith("/settings") }
  ];

  return (
    <main className="shell">
      <section className="mobile-frame" data-hydrated={hydrated ? "true" : "false"}>
        <header className="app-topbar">
          <Link className="brand-lockup" href="/">
            <Image alt="" className="brand-icon" height={40} priority src="/lifepilot-icon.png" width={40} />
            <span className="brand-name">LifePilot</span>
          </Link>
          <Link className="icon-button ghost" href="/settings" title="设置">
            <Settings size={19} />
          </Link>
        </header>
        {children}
        <nav className="app-bottom-nav" aria-label="主导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.label} href={item.href} className={item.active ? "nav-item active" : "nav-item"}>
                <Icon size={20} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </section>
    </main>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1 className="title">{title}</h1>
        {subtitle ? <p className="subtitle">{subtitle}</p> : null}
      </div>
      <div className="row">
        <Link className="icon-button" href="/" title="返回首页">
          <Home size={18} />
        </Link>
        <Link className="icon-button" href="/settings" title="设置">
          <Settings size={18} />
        </Link>
      </div>
    </header>
  );
}
