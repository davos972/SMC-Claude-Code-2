import React from "react";

export default function StartStopButton({ running, onClick, disabled }) {
    return (
        <button
            type="button"
            disabled={disabled}
            onClick={onClick}
            data-testid={running ? "bot-stop-button" : "bot-start-button"}
            className={`relative w-32 h-32 rounded-full flex items-center justify-center text-2xl font-bold tracking-widest transition-all duration-300 active:scale-95 ${
                running
                    ? "bg-panel text-green border-2 border-green shadow-glow-green"
                    : "bg-panel text-gold border-2 border-gold shadow-glow-gold"
            } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
        >
            <span className={`absolute inset-2 rounded-full ${running ? "bg-green/5" : "bg-gold/5"}`} />
            <span className="relative z-10">{running ? "STOP" : "START"}</span>
        </button>
    );
}
