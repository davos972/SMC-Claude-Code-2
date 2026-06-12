import React from "react";
import Header from "./Header";
import BottomNav from "./BottomNav";

export default function AppShell({ children, botState, settings }) {
    return (
        <div className="min-h-screen bg-bg text-text-primary">
            <div className="w-full max-w-[480px] mx-auto relative min-h-screen">
                <Header botState={botState} settings={settings} />
                <main className="px-4 pt-4 pb-28" data-testid="main-content">
                    {children}
                </main>
                <BottomNav />
            </div>
        </div>
    );
}
