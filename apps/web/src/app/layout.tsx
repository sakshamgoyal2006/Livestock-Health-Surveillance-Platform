import type { Metadata, Viewport } from "next";

import { ServiceWorkerLifecycle } from "@/components/ServiceWorkerLifecycle";

import "./styles.css";

export const metadata: Metadata = {
  title: "Pashu Seva — Livestock Health Reports",
  description: "Offline livestock health reporting for veterinary review",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#174f43",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN">
      <body>
        <ServiceWorkerLifecycle />
        {children}
      </body>
    </html>
  );
}
