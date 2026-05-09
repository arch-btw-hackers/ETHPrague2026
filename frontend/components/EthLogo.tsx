// Inline Ethereum diamond mark — vector, no external assets.
// Tinted to fit the dashboard's cool palette by default; pass a `tint`
// override if you need a warmer accent (PDF banner, etc.).

interface Props {
  size?: number;
  tint?: string;
  className?: string;
}

export function EthLogo({ size = 14, tint = "#A4B0FF", className = "" }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 96"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={className}
    >
      <path d="M32 0 L0 52 L32 38 L64 52 Z" fill={tint} fillOpacity={0.95} />
      <path d="M32 0 L32 38 L64 52 Z" fill={tint} fillOpacity={0.55} />
      <path d="M32 96 L0 60 L32 78 L64 60 Z" fill={tint} fillOpacity={0.7} />
      <path d="M32 78 L32 96 L64 60 Z" fill={tint} fillOpacity={0.45} />
    </svg>
  );
}
