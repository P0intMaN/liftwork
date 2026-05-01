import { NavLink } from "react-router-dom";
import { Activity, Boxes, Cpu, LayoutDashboard, LogOut, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";
import { Button } from "@/components/ui/button";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/applications", label: "Applications", icon: Boxes },
  { to: "/clusters", label: "Clusters", icon: Server },
  { to: "/activity", label: "Activity", icon: Activity },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  return (
    <aside className="flex h-full w-60 flex-col border-r border-border bg-card/40 backdrop-blur">
      <div className="flex items-center gap-2 px-5 py-5 text-base font-semibold tracking-tight">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-primary to-info text-primary-foreground shadow">
          <Cpu className="h-3.5 w-3.5" />
        </span>
        liftwork
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-border p-4">
        <p className="truncate text-xs font-medium">{user?.email ?? "—"}</p>
        <p className="truncate text-[11px] uppercase tracking-wider text-muted-foreground">
          {user?.role ?? "guest"}
        </p>
        <Button variant="ghost" size="sm" className="mt-2 w-full justify-start" onClick={logout}>
          <LogOut className="h-4 w-4" /> Sign out
        </Button>
      </div>
    </aside>
  );
}
