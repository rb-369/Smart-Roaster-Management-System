import React from "react";

interface SmartRosterLogoProps {
  size?: number;
  className?: string;
  showWordmark?: boolean;
}

export default function SmartRosterLogo({
  size = 36,
  className = "",
  showWordmark = false,
}: SmartRosterLogoProps) {
  if (showWordmark) {
    return (
      <div className={`inline-flex items-center gap-3 select-none ${className}`}>
        <SmartRosterMark size={size} />
        <div>
          <span className="block text-base sm:text-lg font-extrabold tracking-tight text-neutral-950 leading-tight">
            Smart Roster
          </span>
          <span className="block text-[10px] font-bold tracking-widest text-neutral-400 uppercase leading-none mt-0.5">
            Workforce Intelligence
          </span>
        </div>
      </div>
    );
  }

  return <SmartRosterMark size={size} className={className} />;
}

export function SmartRosterMark({
  size = 36,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 128 128"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`flex-shrink-0 transition-transform duration-200 hover:scale-105 ${className}`}
      aria-label="Smart Roster Logo"
      role="img"
    >
      <defs>
        <linearGradient
          id="srBgGrad"
          x1="12"
          y1="12"
          x2="116"
          y2="120"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#1E40AF" />
          <stop offset="45%" stopColor="#2563EB" />
          <stop offset="85%" stopColor="#0284C7" />
          <stop offset="100%" stopColor="#0D9488" />
        </linearGradient>

        <linearGradient
          id="srGlowGrad"
          x1="16"
          y1="16"
          x2="112"
          y2="36"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0.05" />
        </linearGradient>

        <linearGradient id="srActiveShift" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#34D399" />
          <stop offset="100%" stopColor="#2DD4BF" />
        </linearGradient>

        <linearGradient id="srSparkGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#FDE047" />
          <stop offset="100%" stopColor="#38BDF8" />
        </linearGradient>

        <filter
          id="srDropShadow"
          x="-10%"
          y="-10%"
          width="125%"
          height="135%"
          filterUnits="objectBoundingBox"
        >
          <feDropShadow
            dx="0"
            dy="3"
            stdDeviation="3"
            floodColor="#0F172A"
            floodOpacity="0.25"
          />
        </filter>
      </defs>

      {/* Rounded squircle tile */}
      <rect x="6" y="6" width="116" height="116" rx="28" fill="url(#srBgGrad)" />
      <rect
        x="6.75"
        y="6.75"
        width="114.5"
        height="114.5"
        rx="27.25"
        stroke="url(#srGlowGrad)"
        strokeWidth="1.5"
      />

      {/* Roster Matrix Shifts */}
      <g filter="url(#srDropShadow)">
        {/* Row 1 */}
        <rect
          x="25"
          y="32"
          width="48"
          height="18"
          rx="9"
          fill="#FFFFFF"
          fillOpacity="0.95"
        />
        <circle cx="89" cy="41" r="9" fill="#38BDF8" fillOpacity="0.85" />
        <circle cx="89" cy="41" r="4" fill="#FFFFFF" />

        {/* Sync flow indicator */}
        <path
          d="M64 41 C76 41, 78 55, 68 65"
          stroke="#FFFFFF"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="2 3"
          opacity="0.4"
        />

        {/* Row 2: Active Coverage shift in Teal/Emerald */}
        <rect x="42" y="55" width="61" height="18" rx="9" fill="url(#srActiveShift)" />
        <circle cx="53" cy="64" r="3.5" fill="#FFFFFF" />
        <rect
          x="63"
          y="61.5"
          width="30"
          height="5"
          rx="2.5"
          fill="#FFFFFF"
          fillOpacity="0.85"
        />

        {/* Row 3 */}
        <rect
          x="25"
          y="78"
          width="54"
          height="18"
          rx="9"
          fill="#FFFFFF"
          fillOpacity="0.95"
        />
        <rect
          x="86"
          y="78"
          width="17"
          height="18"
          rx="8.5"
          fill="#FFFFFF"
          fillOpacity="0.3"
          stroke="#FFFFFF"
          strokeWidth="1.5"
        />
      </g>

      {/* Optimizer Spark */}
      <path
        d="M101 16 L103 23 L110 25 L103 27 L101 34 L99 27 L92 25 L99 23 Z"
        fill="url(#srSparkGrad)"
      />
    </svg>
  );
}
