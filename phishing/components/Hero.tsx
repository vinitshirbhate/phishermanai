"use client";

import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import Image from "next/image";

export function Hero() {
  return (
    <section className="relative min-h-screen flex items-center bg-midnight-blue overflow-hidden">
      {/* Background Pattern */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-20 left-20 w-32 h-32 bg-electric-cyan rounded-full blur-3xl" />
        <div className="absolute bottom-20 right-20 w-48 h-48 bg-electric-cyan rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-electric-cyan rounded-full blur-3xl" />
      </div>

      <div className="container mx-auto px-1 py-20 relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 items-center min-h-[80vh] min-w-[95vw]">
          {/* Left Side - Text Content */}
          <motion.div
            className="space-y-16"
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          >
            {/* Headline */}
            <motion.div
              className="space-y-6"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
            >
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-off-white leading-tight">
                Stop AI-powered phishing ———————————{" "}
                <span className="text-electric-cyan">
                  <br />
                  Detect. Deceive. Defeat.
                </span>
              </h1>
            </motion.div>

            {/* Subheadline */}
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4 }}
            >
              <p className="text-lg md:text-xl text-off-white/80 leading-relaxed max-w-lg">
                LLM-aware multi-channel protection (Email, SMS, Voice) with
                adaptive honeypots and takedown-ready evidence.
              </p>
            </motion.div>

            {/* CTAs */}
            <motion.div
              className="space-y-6"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.6 }}
            >
              <div className="flex flex-col sm:flex-row gap-4">
                <Button
                  size="lg"
                  className="text-lg px-8 py-4 bg-sunset-orange text-midnight-blue hover:bg-sunset-orange/90 font-semibold shadow-lg hover:shadow-sunset-orange/25 transition-all duration-300 hover:scale-105"
                  aria-label="Try the demo"
                >
                  Try Demo
                </Button>
                <Button
                  size="lg"
                  className="text-lg px-8 py-4 border border-sunset-orange text-sunset-orange bg-transparent hover:bg-sunset-orange hover:text-midnight-blue transition-all duration-300 hover:scale-105"
                  aria-label="Learn how it works"
                >
                  See How It Works
                </Button>
              </div>
            </motion.div>

            {/* Trust Indicators */}
            <motion.div
              className="space-y-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8, delay: 0.8 }}
            >
              <div className="flex flex-wrap gap-8 text-off-white/60">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 bg-green-500 rounded-full" />
                  <span className="text-sm font-medium">CERT-IN Ready</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 bg-green-500 rounded-full" />
                  <span className="text-sm font-medium">Multi-Channel</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 bg-green-500 rounded-full" />
                  <span className="text-sm font-medium">AI-Resistant</span>
                </div>
              </div>
            </motion.div>
          </motion.div>

          {/* Right Side - India Map Image */}
          <motion.div
            className="flex justify-center lg:justify-center lg:ml-8"
            initial={{ opacity: 0, x: 50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
          >
            <div className="relative w-full max-w-lg">
              <motion.div
                className="relative"
                whileHover={{ scale: 1.05 }}
                transition={{ duration: 0.3 }}
              >
                <Image
                  src="/Screenshot_2025-10-09_194837-removebg-preview.png"
                  alt="India Digital Network Map"
                  width={600}
                  height={600}
                  className="w-full h-auto object-contain"
                  priority
                />
                {/* Subtle glow effect */}
                <div className="absolute inset-0 bg-gradient-to-r from-electric-cyan/10 to-sunset-orange/10 rounded-full blur-3xl -z-10" />
              </motion.div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
