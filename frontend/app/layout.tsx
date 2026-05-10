import type { Metadata } from "next";
import "./globals.css";
import "./map-styles.css";

export const metadata: Metadata = {
  title: "Eliver",
  description: "Real-time monitoring for high-value tokenised shipments.",
  icons: { icon: "/favicon.jpg" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased relative">{children}</body>
    </html>
  );
}
