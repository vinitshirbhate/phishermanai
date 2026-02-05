"use client";

import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Brain, Shield, FileText } from "lucide-react";

const features = [
  {
    icon: Brain,
    title: "LLM-Aware Detection",
    description:
      "Detect AI-crafted phishing with transformer-based intent models.",
    color: "text-electric-cyan",
  },
  {
    icon: Shield,
    title: "Adaptive Honeypots",
    description:
      "Automatically engage attackers via safe, realistic replies to harvest IOCs.",
    color: "text-blue-400",
  },
  {
    icon: FileText,
    title: "Forensic Pack & Takedown",
    description:
      "Get signed evidence (PDF + hash) ready for CERT-IN and registrars.",
    color: "text-sunset-orange",
  },
];

export function Features() {
  return (
    <section className="py-20 bg-midnight-blue-light/30">
      <div className="container mx-auto px-4">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
        >
          <h2 className="text-3xl md:text-4xl font-bold text-off-white mb-4">
            Key Features
          </h2>
          <p className="text-off-white/70 text-lg max-w-2xl mx-auto">
            Advanced protection against sophisticated AI-powered threats
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: index * 0.2 }}
              viewport={{ once: true }}
            >
              <Card className="h-full relative overflow-hidden">
                {/* Glowing border animation - always visible */}
                <div className="absolute inset-0 rounded-lg">
                  {/* Single glowing border animation - clockwise motion */}
                  <div className="absolute inset-0 rounded-lg">
                    {/* Top border */}
                    <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-electric-cyan to-transparent animate-pulse shadow-lg shadow-electric-cyan/50"></div>
                    <div className="absolute top-[-1px] left-0 w-full h-[4px] bg-gradient-to-r from-transparent via-electric-cyan/30 to-transparent animate-pulse blur-sm"></div>

                    {/* Right border */}
                    <div
                      className="absolute top-0 right-0 w-[2px] h-full bg-gradient-to-b from-transparent via-electric-cyan to-transparent animate-pulse shadow-lg shadow-electric-cyan/50"
                      style={{ animationDelay: "0.5s" }}
                    ></div>
                    <div
                      className="absolute top-0 right-[-1px] w-[4px] h-full bg-gradient-to-b from-transparent via-electric-cyan/30 to-transparent animate-pulse blur-sm"
                      style={{ animationDelay: "0.5s" }}
                    ></div>

                    {/* Bottom border */}
                    <div
                      className="absolute bottom-0 right-0 w-full h-[2px] bg-gradient-to-l from-transparent via-electric-cyan to-transparent animate-pulse shadow-lg shadow-electric-cyan/50"
                      style={{ animationDelay: "1s" }}
                    ></div>
                    <div
                      className="absolute bottom-[-1px] right-0 w-full h-[4px] bg-gradient-to-l from-transparent via-electric-cyan/30 to-transparent animate-pulse blur-sm"
                      style={{ animationDelay: "1s" }}
                    ></div>

                    {/* Left border */}
                    <div
                      className="absolute bottom-0 left-0 w-[2px] h-full bg-gradient-to-t from-transparent via-electric-cyan to-transparent animate-pulse shadow-lg shadow-electric-cyan/50"
                      style={{ animationDelay: "1.5s" }}
                    ></div>
                    <div
                      className="absolute bottom-0 left-[-1px] w-[4px] h-full bg-gradient-to-t from-transparent via-electric-cyan/30 to-transparent animate-pulse blur-sm"
                      style={{ animationDelay: "1.5s" }}
                    ></div>
                  </div>
                </div>
                <CardHeader className="text-center relative z-10">
                  <div
                    className={`w-16 h-16 mx-auto mb-4 rounded-full bg-midnight-blue-light/50 flex items-center justify-center ${feature.color}`}
                  >
                    <feature.icon className="w-8 h-8" />
                  </div>
                  <CardTitle className="text-xl text-off-white">
                    {feature.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="relative z-10">
                  <p className="text-off-white/70 text-center leading-relaxed">
                    {feature.description}
                  </p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
