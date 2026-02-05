"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

export default function Header() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-[#0a1628]/90 backdrop-blur-sm border-b border-white/10">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo + Title */}
          <Link href="/" className="flex items-center gap-3">
            <Image
              src="/logo.png"
              alt="OMINIS"
              width={140}
              height={40}
              className="h-7 w-auto"
              priority
            />
            <span className="hidden md:inline text-gray-300 text-xs border-l border-white/20 pl-3">
              Observatorio Mexicano para la Investigación y la Inteligencia en Salud
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-8">
            <Link 
              href="https://ominis.org" 
              target="_blank"
              className="text-gray-300 hover:text-white transition-colors text-sm"
            >
              Observatorio
            </Link>
            <Link 
              href="https://roclab.ominis.org" 
              target="_blank"
              className="text-gray-300 hover:text-white transition-colors text-sm"
            >
              ROCLab
            </Link>
            <Link 
              href="https://funsalud.org.mx" 
              target="_blank"
              className="text-gray-300 hover:text-white transition-colors text-sm"
            >
              FUNSALUD
            </Link>
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden text-white p-2"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label="Toggle menu"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              {isMenuOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile Navigation */}
        {isMenuOpen && (
          <div className="md:hidden py-4 border-t border-white/10">
            <div className="flex flex-col gap-4">
              <Link 
                href="https://ominis.org" 
                target="_blank"
                className="text-gray-300 hover:text-white transition-colors"
              >
                Observatorio
              </Link>
              <Link 
                href="https://roclab.ominis.org" 
                target="_blank"
                className="text-gray-300 hover:text-white transition-colors"
              >
                ROCLab
              </Link>
              <Link 
                href="https://funsalud.org.mx" 
                target="_blank"
                className="text-gray-300 hover:text-white transition-colors"
              >
                FUNSALUD
              </Link>
            </div>
          </div>
        )}
      </nav>
    </header>
  );
}
