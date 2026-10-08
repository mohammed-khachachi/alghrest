import Link from "next/link";
export default function NotFound() {
 return <main className="error-page"><p className="eyebrow">404 / ALGHREST</p><h1>هذه الصفحة غير موجودة.</h1><p>يمكنك متابعة استكشاف المشروع من الصفحة الرئيسية.</p><Link className="button primary" href="/">العودة إلى الموقع</Link></main>;
}

