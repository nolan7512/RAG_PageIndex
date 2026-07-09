import "./globals.css";

export const metadata = {
  title: "RAG PageIndex",
  description: "Internal RAG document workbench"
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
