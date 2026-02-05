"use client";

import { motion } from "framer-motion";
import { ArrowRight, Mail, Brain, Shield } from "lucide-react";

const steps = [
  {
    icon: Mail,
    title: "Ingest",
    description: "Email, SMS, Voice → normalized & analyzed",
    color: "text-electric-cyan",
  },
  {
    icon: Brain,
    title: "Decide",
    description: "Block / Honeypot / Deliver with warning",
    color: "text-blue-400",
  },
  {
    icon: Shield,
    title: "Act",
    description: "Sandbox, enrich, anchor hash on-chain, prepare takedown",
    color: "text-sunset-orange",
  },
];

export function HowItWorks() {
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
            How It Works
          </h2>
          <p className="text-off-white/70 text-lg max-w-2xl mx-auto">
            Three-step process to detect, deceive, and defeat AI-powered threats
          </p>
        </motion.div>

        <div className="max-w-5xl mx-auto">
          {/* Desktop Flow */}
          <div className="hidden md:flex items-center justify-between">
            {steps.map((step, index) => (
              <motion.div
                key={step.title}
                className="flex flex-col items-center text-center flex-1"
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, delay: index * 0.2 }}
                viewport={{ once: true }}
              >
                <motion.div
                  className={`w-20 h-20 rounded-full bg-midnight-blue-light/50 flex items-center justify-center mb-6 ${step.color} border-2 border-gray-700 hover:border-electric-cyan/50 transition-all duration-300`}
                  whileHover={{ scale: 1.1, rotate: 5 }}
                >
                  <step.icon className="w-10 h-10" />
                </motion.div>

                <h3 className="text-xl font-semibold text-off-white mb-2">
                  {step.title}
                </h3>
                <p className="text-off-white/70 text-sm max-w-xs leading-relaxed">
                  {step.description}
                </p>

                {/* Arrow between steps */}
                {index < steps.length - 1 && (
                  <motion.div
                    className="absolute right-0 top-10 transform translate-x-1/2"
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.8, delay: index * 0.2 + 0.4 }}
                    viewport={{ once: true }}
                  >
                    <ArrowRight className="w-6 h-6 text-electric-cyan" />
                  </motion.div>
                )}
              </motion.div>
            ))}
          </div>

          {/* Mobile Flow */}
          <div className="md:hidden space-y-8">
            {steps.map((step, index) => (
              <motion.div
                key={step.title}
                className="flex items-center space-x-4"
                initial={{ opacity: 0, x: -30 }}
                whileInView={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.8, delay: index * 0.2 }}
                viewport={{ once: true }}
              >
                <motion.div
                  className={`w-16 h-16 rounded-full bg-midnight-blue-light/50 flex items-center justify-center ${step.color} border-2 border-gray-700 hover:border-electric-cyan/50 transition-all duration-300 flex-shrink-0`}
                  whileHover={{ scale: 1.1 }}
                >
                  <step.icon className="w-8 h-8" />
                </motion.div>

                <div>
                  <h3 className="text-lg font-semibold text-off-white mb-1">
                    {step.title}
                  </h3>
                  <p className="text-off-white/70 text-sm leading-relaxed">
                    {step.description}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
