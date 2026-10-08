import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
const arabic = localFont({ src: "../public/fonts/NotoSansArabic.ttf", variable: "--font-arabic", display: "swap", weight: "100 900" });
const inter = localFont({ src: "../public/fonts/Inter-Regular.ttf", variable: "--font-latin", display: "swap", weight: "400" });
export const metadata: Metadata = {
  title: { default: "ALGHREST — الذكاء يقرأ. أنت تقرر.", template: "%s · ALGHREST" },
  description: "استكشف بنية ALGHREST، منصة بحث ودعم قرار للتداول: بيانات موثقة، مخاطرة حتمية، وإعادة تشغيل قابلة للفحص.",
  robots: { index: false, follow: false },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ar" dir="rtl"><body className={arabic.variable + " " + inter.variable}>{children}</body></html>;
}
