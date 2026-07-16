// Purpose: define the Next.js root document shell. Responsibilities: load global styles and provide application metadata. Future modules: add providers only when shared client state or data fetching requires them.
import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import '../styles/globals.css';

export const metadata: Metadata = {
  title: 'DeceptiForge',
  description: 'Context-aware deception platform for AI-era security.',
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
