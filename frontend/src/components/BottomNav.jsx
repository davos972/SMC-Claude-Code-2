import React from "react";
import { NavLink } from "react-router-dom";
import { LayoutDashboard, History, BarChart3, Settings as SettingsIcon } from "lucide-react";

const tabs = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, testid: "tab-dashboard" },
    { to: "/backtest", label: "Backtest", icon: History, testid: "tab-backtest" },
    { to: "/stats", label: "Stats", icon: BarChart3, testid: "tab-stats" },
    { to: "/settings", label: "Réglages", icon: SettingsIcon, testid: "tab-settings" },
];

export default function BottomNav() {
    return (
        <nav className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-[480px] z-40 bg-panel/95 backdrop-blur-md border-t border-bd"
             data-testid="bottom-nav"
             style={{ paddingBottom: "max(env(safe-area-inset-bottom), 0px)" }}>
            <div className="grid grid-cols-4 px-2 py-2">
                {tabs.map(({ to, label, icon: Icon, testid }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={to === "/"}
                        className={({ isActive }) =>
                            `flex flex-col items-center gap-1 p-2 rounded-xl transition-colors ${
                                isActive ? "text-gold" : "text-text-secondary hover:text-text-primary"
                            }`
                        }
                        data-testid={testid}
                    >
                        {({ isActive }) => (
                            <>
                                <Icon className="w-5 h-5" strokeWidth={isActive ? 2.5 : 2} fill={isActive && to === "/" ? "currentColor" : "none"} />
                                <span className="text-[11px] font-medium tracking-wide">{label}</span>
                            </>
                        )}
                    </NavLink>
                ))}
            </div>
        </nav>
    );
}
