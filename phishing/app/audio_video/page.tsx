"use client";
import { useState, useRef } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Upload,
  FileAudio,
  FileVideo,
  Download,
  AlertTriangle,
  CheckCircle,
  Clock,
} from "lucide-react";

interface TranscriptSegment {
  speaker: string;
  text: string;
  start_time: number;
  end_time: number;
}

interface TranscriptionResult {
  transcript_id: string;
  pdf_url?: string;
  transcription: TranscriptSegment[];
  phishing_detected: boolean;
  phishing_score: number;
  suspicious_phrases: string[];
  label: string;
  confidence: number;
  created_at?: string;
  original_file?: string;
  nft_transaction_hash?: string;
  nft_gateway_url?: string;
}

export default function AudioVideoPage() {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [transcriptionResult, setTranscriptionResult] =
    useState<TranscriptionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<TranscriptionResult[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setError(null);
      setTranscriptionResult(null);
    }
  };

  const loadHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const response = await fetch("http://localhost:8000/transcripts/");
      if (response.ok) {
        const transcripts = await response.json();
        console.log(transcripts);
        
        const formattedHistory = transcripts.map((transcript: any) => ({
          transcript_id: transcript._id,
          pdf_url: transcript.pdf_path
            ? `/download/${transcript.pdf_path.split("/").pop()}`
            : "",
          transcription: transcript.transcription || [],
          phishing_detected: transcript.is_phishing || false,
          phishing_score: Math.round((transcript.confidence || 0) * 100),
          suspicious_phrases: transcript.is_phishing
            ? ["Phishing detected by AI model"]
            : [],
          label: transcript.label || "unknown",
          confidence: transcript.confidence || 0,
          created_at: transcript.created_at,
          original_file: transcript.original_file,
          nft_transaction_hash: transcript.nft_transaction_hash,
          nft_gateway_url: transcript.nft_gateway_url,
        }));
        setHistory(formattedHistory);
      }
    } catch (err) {
      console.error("Failed to load history:", err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select a file");
      return;
    }

    setIsUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    // Upload file to NFT API
    let nftTransactionHash: string | undefined;
    let nftGatewayUrl: string | undefined;
    
    try {
      const nftFormData = new FormData();
      nftFormData.append("file", file);
      
      const nftResponse = await fetch(
        "https://vanadous-evon-formerly.ngrok-free.dev/api/upload",
        {
          method: "POST",
          body: nftFormData,
        }
      );

      if (nftResponse.ok) {
        const nftResult = await nftResponse.json();
        nftTransactionHash = nftResult.transactionHash || nftResult.transaction_hash || nftResult.hash;
        nftGatewayUrl = nftResult.gatewayUrl || nftResult.gateway_url || nftResult.gateway || nftResult.url;
        console.log("NFT data received:", { nftTransactionHash, nftGatewayUrl });
      } else {
        console.error("NFT API upload failed:", nftResponse.status);
      }
    } catch (nftError) {
      console.error("Error uploading to NFT API:", nftError);
      // Continue even if NFT upload fails
    }

    try {
      const response = await fetch("http://localhost:8000/transcribe/", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();

      // Get the full transcript from the API
      const transcriptResponse = await fetch(
        `http://localhost:8000/transcript/${result.transcript_id}`
      );
      if (transcriptResponse.ok) {
        const transcriptData = await transcriptResponse.json();

        const detection =
          transcriptData.phishing_detection || result.phishing_detection || {};
        const isPhishing = Boolean(detection.is_phishing);
        const confidence =
          typeof detection.confidence === "number" ? detection.confidence : 0;
        const label = detection.label || "unknown";
        const pdfUrl = transcriptData.pdf_path
          ? `/download/${transcriptData.pdf_path.split("/").pop()}`
          : result.pdf_url || "";

        const newResult = {
          transcript_id: result.transcript_id,
          pdf_url: pdfUrl,
          transcription: transcriptData.transcription || [],
          phishing_detected: isPhishing,
          phishing_score: Math.round(confidence * 100),
          suspicious_phrases: isPhishing
            ? ["Phishing detected by AI model"]
            : [],
          label,
          confidence,
          created_at: new Date().toISOString(),
          original_file: file.name,
          nft_transaction_hash: nftTransactionHash,
          nft_gateway_url: nftGatewayUrl,
        };

        setTranscriptionResult(newResult);
        setHistory((prev) => [newResult, ...prev]);
      } else {
        // Fallback if transcript fetch fails
        const detection = result.phishing_detection || {};
        const isPhishing = Boolean(detection.is_phishing);
        const confidence =
          typeof detection.confidence === "number" ? detection.confidence : 0;
        const label = detection.label || "unknown";

        setTranscriptionResult({
          transcript_id: result.transcript_id,
          pdf_url: result.pdf_url || "",
          transcription: [],
          phishing_detected: isPhishing,
          phishing_score: Math.round(confidence * 100),
          suspicious_phrases: isPhishing
            ? ["Phishing detected by AI model"]
            : [],
          label,
          confidence,
          nft_transaction_hash: nftTransactionHash,
          nft_gateway_url: nftGatewayUrl,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  const handlePdfDownload = async (transcriptId: string) => {
    const newWindow = window.open("", "_blank");
    if (!newWindow) {
      setError("Please allow popups to download the PDF");
      return;
    }

    try {
      // Get NFT data from current transcription result or history
      const currentResult = transcriptionResult?.transcript_id === transcriptId 
        ? transcriptionResult 
        : history.find(h => h.transcript_id === transcriptId);
      
      const nftHash = currentResult?.nft_transaction_hash || "";
      const nftUrl = currentResult?.nft_gateway_url || "";
      
      // Build query string with NFT data
      const params = new URLSearchParams({
        transcriptId: transcriptId,
      });
      if (nftHash) params.append("nftHash", nftHash);
      if (nftUrl) params.append("nftUrl", nftUrl);

      const response = await fetch(
        `/api/generate-pdf-with-nft?${params.toString()}`
      );

      if (!response.ok) {
        throw new Error(`Failed to generate PDF (status ${response.status})`);
      }

      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      newWindow.location.href = blobUrl;

      setTimeout(() => {
        window.URL.revokeObjectURL(blobUrl);
      }, 60_000);
    } catch (err) {
      newWindow.close();
      setError(
        err instanceof Error ? err.message : "Failed to generate the PDF"
      );
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="min-h-screen bg-midnight-blue py-20">
      <div className="container mx-auto px-4">
        <motion.div
          className="text-center mb-12"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <h1 className="text-4xl md:text-5xl font-bold text-off-white mb-4">
            Audio/Video Transcription
          </h1>
          <p className="text-off-white/70 text-lg max-w-2xl mx-auto">
            Upload audio or video files to transcribe and detect potential
            phishing attempts
          </p>
        </motion.div>

        <div className="max-w-4xl mx-auto">
          {/* Upload Section */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
          >
            <Card className="mb-8 bg-midnight-blue-light/20 border-midnight-blue-light/30">
              <CardHeader>
                <CardTitle className="text-xl text-off-white flex items-center gap-2">
                  <Upload className="w-5 h-5" />
                  Upload Media File
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* File Upload */}
                <div>
                  <label className="block text-sm font-medium text-off-white mb-2">
                    Select Audio/Video File
                  </label>
                  <div
                    className="border-2 border-dashed border-electric-cyan/50 rounded-lg p-8 text-center cursor-pointer hover:border-electric-cyan transition-colors"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {file ? (
                      <div className="space-y-2">
                        {file.type.startsWith("video/") ? (
                          <FileVideo className="w-12 h-12 mx-auto text-electric-cyan" />
                        ) : (
                          <FileAudio className="w-12 h-12 mx-auto text-electric-cyan" />
                        )}
                        <p className="text-off-white font-medium">
                          {file.name}
                        </p>
                        <p className="text-off-white/60 text-sm">
                          {(file.size / (1024 * 1024)).toFixed(2)} MB
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Upload className="w-12 h-12 mx-auto text-electric-cyan/50" />
                        <p className="text-off-white">
                          Click to upload or drag and drop
                        </p>
                        <p className="text-off-white/60 text-sm">
                          Supports MP3, WAV, MP4, AVI, MOV formats
                        </p>
                      </div>
                    )}
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*,video/*"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </div>

                {/* File Preview */}
                {file && (
                  <div className="p-4 bg-midnight-blue-light/10 rounded-lg border border-electric-cyan/30">
                    <h4 className="text-off-white font-medium mb-3 flex items-center gap-2">
                      {file.type.startsWith("video/") ? (
                        <FileVideo className="w-4 h-4" />
                      ) : (
                        <FileAudio className="w-4 h-4" />
                      )}
                      File Preview
                    </h4>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-off-white/70 text-sm">
                          File Name:
                        </span>
                        <span className="text-off-white text-sm font-medium">
                          {file.name}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-off-white/70 text-sm">
                          File Size:
                        </span>
                        <span className="text-off-white text-sm font-medium">
                          {(file.size / (1024 * 1024)).toFixed(2)} MB
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-off-white/70 text-sm">
                          File Type:
                        </span>
                        <span className="text-off-white text-sm font-medium">
                          {file.type || "Unknown"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-off-white/70 text-sm">
                          Last Modified:
                        </span>
                        <span className="text-off-white text-sm font-medium">
                          {new Date(file.lastModified).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Upload Button */}
                <Button
                  onClick={handleUpload}
                  disabled={isUploading || !file}
                  className="w-full bg-electric-cyan text-midnight-blue hover:bg-electric-cyan/90 font-semibold py-3"
                >
                  {isUploading ? (
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 animate-spin" />
                      Processing...
                    </div>
                  ) : (
                    "Start Transcription & Analysis"
                  )}
                </Button>

                {error && (
                  <div className="p-4 bg-red-500/20 border border-red-500/50 rounded-md">
                    <p className="text-red-400">{error}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* History Section */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
          >
            <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xl text-off-white flex items-center gap-2">
                    <Clock className="w-5 h-5" />
                    Transcription History
                  </CardTitle>
                  <Button
                    onClick={loadHistory}
                    disabled={isLoadingHistory}
                    variant="outline"
                    size="sm"
                    className="text-electric-cyan border-electric-cyan hover:bg-electric-cyan hover:text-midnight-blue"
                  >
                    {isLoadingHistory ? (
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 border border-electric-cyan border-t-transparent rounded-full animate-spin" />
                        Loading...
                      </div>
                    ) : (
                      "Refresh"
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {history.length === 0 ? (
                  <div className="text-center py-8">
                    <Clock className="w-12 h-12 mx-auto text-electric-cyan/50 mb-4" />
                    <p className="text-off-white/70">
                      No transcription history yet
                    </p>
                    <p className="text-off-white/50 text-sm">
                      Upload a file to see your history here
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {history.map((item, index) => (
                      <div
                        key={item.transcript_id}
                        className="p-4 bg-midnight-blue-light/10 rounded-lg border border-midnight-blue-light/20 hover:border-electric-cyan/50 transition-colors cursor-pointer"
                        onClick={() => setTranscriptionResult(item)}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-3">
                            <div
                              className={`w-3 h-3 rounded-full ${
                                item.phishing_detected
                                  ? "bg-red-400"
                                  : "bg-green-400"
                              }`}
                            />
                            <span className="text-off-white font-medium">
                              {item.original_file ||
                                `Transcription ${index + 1}`}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-sm font-semibold ${
                                item.phishing_detected
                                  ? "text-red-400"
                                  : "text-green-400"
                              }`}
                            >
                              {item.phishing_score}%
                            </span>
                            <span className="text-off-white/60 text-xs">
                              {item.created_at
                                ? new Date(item.created_at).toLocaleDateString()
                                : "Unknown date"}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-off-white/70">
                            {item.transcription.length} segments • {item.label}
                          </span>
                          {item.transcript_id && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-electric-cyan hover:text-electric-cyan/80"
                              onClick={(e) => {
                                e.stopPropagation();
                                handlePdfDownload(item.transcript_id);
                              }}
                            >
                              <Download className="w-3 h-3 mr-1" />
                              PDF
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Results Section */}
          {transcriptionResult && (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4 }}
              className="space-y-6"
            >
              {/* Phishing Detection Results */}
              <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
                <CardHeader>
                  <CardTitle className="text-xl text-off-white flex items-center gap-2">
                    {transcriptionResult.phishing_detected ? (
                      <AlertTriangle className="w-5 h-5 text-red-400" />
                    ) : (
                      <CheckCircle className="w-5 h-5 text-green-400" />
                    )}
                    Phishing Detection Results
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid md:grid-cols-3 gap-4 mb-4">
                    <div className="text-center">
                      <div
                        className={`text-2xl font-bold ${
                          transcriptionResult.phishing_detected
                            ? "text-red-400"
                            : "text-green-400"
                        }`}
                      >
                        {transcriptionResult.phishing_score}%
                      </div>
                      <div className="text-off-white/70 text-sm">
                        Risk Score
                      </div>
                    </div>
                    <div className="text-center">
                      <div
                        className={`text-lg font-semibold ${
                          transcriptionResult.phishing_detected
                            ? "text-red-400"
                            : "text-green-400"
                        }`}
                      >
                        {transcriptionResult.phishing_detected
                          ? "HIGH RISK"
                          : "SAFE"}
                      </div>
                      <div className="text-off-white/70 text-sm">Status</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-semibold text-electric-cyan">
                        {transcriptionResult.suspicious_phrases.length}
                      </div>
                      <div className="text-off-white/70 text-sm">
                        Suspicious Phrases
                      </div>
                    </div>
                  </div>

                  <div className="mb-4">
                    <h4 className="text-off-white font-medium mb-2">
                      AI Detection Details:
                    </h4>
                    <div className="grid md:grid-cols-2 gap-4">
                      <div>
                        <span className="text-off-white/70 text-sm">
                          Model Label:{" "}
                        </span>
                        <span
                          className={`font-semibold ${
                            transcriptionResult.phishing_detected
                              ? "text-red-400"
                              : "text-green-400"
                          }`}
                        >
                          {transcriptionResult.label}
                        </span>
                      </div>
                      <div>
                        <span className="text-off-white/70 text-sm">
                          Confidence:{" "}
                        </span>
                        <span
                          className={`font-semibold ${
                            transcriptionResult.phishing_detected
                              ? "text-red-400"
                              : "text-green-400"
                          }`}
                        >
                          {(transcriptionResult.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </div>

                  {transcriptionResult.suspicious_phrases.length > 0 && (
                    <div>
                      <h4 className="text-off-white font-medium mb-2">
                        Detection Summary:
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {transcriptionResult.suspicious_phrases.map(
                          (phrase, index) => (
                            <span
                              key={index}
                              className="px-3 py-1 bg-red-500/20 text-red-400 rounded-full text-sm"
                            >
                              {phrase}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  <div className="mt-4 flex gap-4">
                    <Button
                      onClick={() =>
                        handlePdfDownload(transcriptionResult.transcript_id)
                      }
                      className="bg-sunset-orange text-midnight-blue hover:bg-sunset-orange/90"
                    >
                      <Download className="w-4 h-4 mr-2" />
                      Download PDF
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Transcription Results */}
              <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
                <CardHeader>
                  <CardTitle className="text-xl text-off-white">
                    Transcription
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {transcriptionResult.transcription?.map(
                      (segment, index) => (
                        <div
                          key={index}
                          className="border-l-2 border-electric-cyan/50 pl-4"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-electric-cyan font-semibold">
                              Speaker {segment.speaker}
                            </span>
                            <span className="text-off-white/60 text-sm">
                              {formatTime(segment.start_time)} -{" "}
                              {formatTime(segment.end_time)}
                            </span>
                          </div>
                          <p className="text-off-white/80">{segment.text}</p>
                        </div>
                      )
                    )}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
