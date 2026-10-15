import { useState } from "react";

import defaultLogo from "../assets/aveon-logo.svg";

const configuredLogo = (import.meta.env.VITE_BRAND_LOGO_URL || "/branding/logo.png").trim();

type BrandLogoProps = {
  className?: string;
  alt?: string;
};

export function BrandLogo({ className, alt = "Brand Logo" }: BrandLogoProps) {
  const initialSrc = configuredLogo || defaultLogo;
  const [src, setSrc] = useState(initialSrc);

  return (
    <img
      src={src}
      alt={alt}
      className={className}
      onError={() => {
        if (src !== defaultLogo) {
          setSrc(defaultLogo);
        }
      }}
    />
  );
}
