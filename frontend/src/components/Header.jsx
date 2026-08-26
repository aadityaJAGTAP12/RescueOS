import { Link, useLocation } from "react-router-dom";
import { Shield, Activity, LayoutDashboard, FileText } from "lucide-react";
import { cn } from "../lib/utils";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/field-intelligence", label: "Field Intelligence", icon: FileText },
];

export default function Header() {
  const location = useLocation();

  return (
    <header className="border-b border-stone-200 bg-white/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-3 no-underline">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-stone-900">
                <Shield className="w-4.5 h-4.5 text-white" strokeWidth={2.5} />
              </div>
              <div className="flex items-baseline gap-2">
                <h1 className="text-[15px] font-semibold tracking-tight text-stone-900">
                  ReliefOS
                </h1>
                <span className="hidden sm:inline text-[13px] text-stone-400 font-medium">
                  Emergency Operations Intelligence
                </span>
              </div>
            </Link>
          </div>

          {/* Navigation */}
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const isActive = location.pathname === item.path;
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[13px] font-medium transition-all duration-200 no-underline",
                    isActive
                      ? "bg-stone-100 text-stone-900"
                      : "text-stone-500 hover:bg-stone-50 hover:text-stone-700"
                  )}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}

            {/* Status badge */}
            <div className="ml-2 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-green-50 border border-green-200/60">
              <Activity className="w-3 h-3 text-green-600" />
              <span className="text-[11px] font-semibold text-green-700 uppercase tracking-wider">
                Active
              </span>
            </div>
          </nav>
        </div>
      </div>
    </header>
  );
}
