import logoUrl from "../../../assets/logo.png";

export function BrandLogo({
  size = "normal",
  className = "",
}: {
  size?: "normal" | "large";
  className?: string;
}) {
  return (
    <img
      className={`brand-logo brand-logo-${size} ${className}`.trim()}
      src={logoUrl}
      alt=""
      aria-hidden="true"
      draggable={false}
    />
  );
}
