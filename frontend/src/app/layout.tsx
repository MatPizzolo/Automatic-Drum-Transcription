import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/providers/theme-provider";
import { QueryProvider } from "@/providers/query-provider";
import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { Toaster } from "@/components/ui/sonner";
import { OfflineBanner } from "@/components/layout/offline-banner";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DrumScribe — AI Drum Transcription",
  description:
    "Turn any song into drum sheet music with AI. Upload an audio file or paste a YouTube URL and get accurate drum notation in seconds.",
  openGraph: {
    title: "DrumScribe — AI Drum Transcription",
    description:
      "Turn any song into drum sheet music with AI.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "DrumScribe — AI Drum Transcription",
    description:
      "Turn any song into drum sheet music with AI.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}
      >
        <ThemeProvider>
          <QueryProvider>
            <div className="flex min-h-screen flex-col">
              <OfflineBanner />
              <Header />
              <main className="flex-1">{children}</main>
              <Footer />
            </div>
            <Toaster richColors position="bottom-right" />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
