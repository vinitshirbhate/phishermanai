"use client";

import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, Shield, AlertTriangle, Target } from "lucide-react";

const importanceData = [
  {
    icon: TrendingUp,
    title: "₹220 Million Average Cost",
    description:
      "In 2025, the average cost of a data breach in India hit ₹220 million (~₹22 crore) — a 13% year-on-year rise.",
    source: "IBM India News Room",
    color: "text-red-400",
    stat: "₹220M",
  },
  {
    icon: Target,
    title: "18% of Breaches",
    description:
      "18% of data breaches in India stem from phishing, making it the top attack vector.",
    source: "Business Today",
    color: "text-orange-400",
    stat: "18%",
  },
  {
    icon: AlertTriangle,
    title: "₹22,845 Crore Lost",
    description: "Over ₹22,845 crore lost to cybercriminals in 2024 alone.",
    source: "The Economic Times",
    color: "text-yellow-400",
    stat: "₹22,845Cr",
  },
  {
    icon: Shield,
    title: "500-900% Surge",
    description: "500–900% surge in phishing attempts within 18 months.",
    source: "The Economic Times",
    color: "text-green-400",
    stat: "900%",
  },
];

export function WhyItMatters() {
  return (
    <section className="py-20 bg-midnight-blue">
      <div className="container mx-auto px-4">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
        >
          <h2 className="text-3xl md:text-4xl font-bold text-off-white mb-4">
            Why It's Important
          </h2>
          <p className="text-off-white/70 text-lg max-w-2xl mx-auto">
            The alarming statistics that highlight the critical need for
            advanced phishing protection
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-7xl mx-auto">
          {importanceData.map((data, index) => (
            <motion.div
              key={data.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: index * 0.1 }}
              viewport={{ once: true }}
            >
              <Card className="h-full relative overflow-hidden bg-midnight-blue-light/20 border-midnight-blue-light/30">
                {/* Single glowing border animation - clockwise motion */}
                <div className="absolute inset-0 rounded-lg">
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

                <CardHeader className="text-center relative z-10 pb-4">
                  <div
                    className={`w-12 h-12 mx-auto mb-3 rounded-full bg-midnight-blue-light/50 flex items-center justify-center ${data.color}`}
                  >
                    <data.icon className="w-6 h-6" />
                  </div>
                  <div className="text-2xl font-bold text-off-white mb-2">
                    {data.stat}
                  </div>
                  <CardTitle className="text-lg text-off-white leading-tight">
                    {data.title}
                  </CardTitle>
                </CardHeader>

                <CardContent className="relative z-10 pt-0">
                  <p className="text-off-white/80 text-sm leading-relaxed mb-3">
                    {data.description}
                  </p>
                  <div className="text-xs text-off-white/60 italic border-t border-off-white/20 pt-2">
                    Source: {data.source}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
