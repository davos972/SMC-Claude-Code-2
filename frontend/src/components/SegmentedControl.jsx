import React from "react";

export default function SegmentedControl({ options, value, onChange, testid }) {
    return (
        <div className="flex p-1 bg-bg rounded-xl border border-bd" data-testid={testid}>
            {options.map((opt) => {
                const active = opt.value === value;
                const disabled = opt.disabled;
                return (
                    <button
                        key={opt.value}
                        type="button"
                        disabled={disabled}
                        onClick={() => !disabled && onChange(opt.value)}
                        data-testid={`${testid}-${opt.value}`}
                        className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all flex items-center justify-center gap-1.5 ${
                            active
                                ? "bg-panel text-gold shadow-sm border border-gold/30"
                                : "text-text-secondary hover:text-text-primary"
                        } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
                    >
                        {opt.icon}
                        <span>{opt.label}</span>
                    </button>
                );
            })}
        </div>
    );
}
