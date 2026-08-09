import "./globals.css";

export const metadata = {
  title: "Enterprise Document Intelligence | vLLM + Qdrant + Redis",
  description:
    "Private enterprise RAG system: self-hosted vLLM inference, Qdrant hybrid vector search, Redis semantic caching, RBAC document security.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
