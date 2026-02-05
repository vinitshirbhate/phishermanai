import { NextRequest, NextResponse } from "next/server";
import { jsPDF } from "jspdf";

export async function GET(request: NextRequest) {

  const TRANSCRIPTION_URL = process.env.NEXT_PUBLIC_TRANSCRIPTION_URL! 
  try {
    const { searchParams } = new URL(request.url);
    const transcriptId = searchParams.get("transcriptId");

    if (!transcriptId) {
      return NextResponse.json(
        { error: "transcriptId is required" },
        { status: 400 }
      );
    }

    // Step 1: Get NFT data from query parameters (passed from frontend)
    const nftHash = searchParams.get("nftHash");
    const nftUrl = searchParams.get("nftUrl");
    const nftData: { transactionHash?: string; gatewayUrl?: string } = {
      transactionHash: nftHash || undefined,
      gatewayUrl: nftUrl || undefined,
    };
    console.log("NFT data from query params:", nftData);

    // Step 2: Fetch transcript data from backend
    const transcriptResponse = await fetch(
      `${TRANSCRIPTION_URL}/transcript/${transcriptId}`
    );

    if (!transcriptResponse.ok) {
      return NextResponse.json(
        { error: "Failed to fetch transcript" },
        { status: transcriptResponse.status }
      );
    }

    const transcriptData = await transcriptResponse.json();
    console.log("Transcript data:", JSON.stringify(transcriptData, null, 2));

    // Step 3: Generate PDF with transcript and NFT data
    const doc = new jsPDF();
    const margin = 15;
    let y = margin;

    const ensureSpace = (height = 6) => {
      if (y + height > 280) {
        doc.addPage();
        y = margin;
      }
    };

    const addTitle = (text: string) => {
      ensureSpace(10);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(20);
      const pageWidth = doc.internal.pageSize.getWidth();
      doc.text(text, pageWidth / 2, y, { align: "center" });
      y += 10;
    };

    const addHeading = (text: string) => {
      ensureSpace(8);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(16);
      doc.text(text, margin, y);
      y += 8;
    };

    const addText = (text: string, fontSize = 12, isBold = false) => {
      doc.setFont("helvetica", isBold ? "bold" : "normal");
      doc.setFontSize(fontSize);
      const lines = doc.splitTextToSize(text, 180);
      lines.forEach((line: string) => {
        ensureSpace();
        doc.text(line, margin, y);
        y += 6;
      });
      y += 2;
    };

    const addSeparator = () => {
      ensureSpace(4);
      doc.setDrawColor(200);
      doc.line(margin, y, 195, y);
      y += 4;
    };

    // Add title
    addTitle("Transcription Report");

    // Add NFT Information section - always show, even if empty
    addHeading("NFT Verification");
    
    if (nftData.transactionHash) {
      addText(`Transaction Hash: ${nftData.transactionHash}`, 12);
    } else {
      addText("Transaction Hash: Not available", 12);
    }

    if (nftData.gatewayUrl) {
      addText(`Gateway URL: ${nftData.gatewayUrl}`, 12);
    } else {
      addText("Gateway URL: Not available", 12);
    }

    addSeparator();

    // Add metadata
    addHeading("Report Information");
    addText(`Transcript ID: ${transcriptId}`, 12);

    if (transcriptData.original_file) {
      addText(`Original File: ${transcriptData.original_file}`, 12);
    }

    if (transcriptData.created_at) {
      addText(
        `Created At: ${new Date(transcriptData.created_at).toLocaleString()}`,
        12
      );
    }

    addSeparator();

    // Add phishing detection results
    // Check both nested phishing_detection object and direct fields
    const phishingDetection = transcriptData.phishing_detection || {};
    const isPhishing = Boolean(
      phishingDetection.is_phishing !== undefined 
        ? phishingDetection.is_phishing 
        : transcriptData.is_phishing !== undefined 
        ? transcriptData.is_phishing 
        : false
    );
    const confidence = 
      phishingDetection.confidence !== undefined 
        ? phishingDetection.confidence 
        : transcriptData.confidence !== undefined 
        ? transcriptData.confidence 
        : 0;
    const label = 
      phishingDetection.label || transcriptData.label || "unknown";
    
    console.log("Phishing detection:", {
      isPhishing,
      confidence,
      label,
      phishingDetection,
      transcriptDataIsPhishing: transcriptData.is_phishing,
      transcriptDataConfidence: transcriptData.confidence,
    });

    addHeading("Phishing Detection Results");
    addText(
      `Status: ${isPhishing ? "HIGH RISK - Phishing Detected" : "SAFE"}`,
      12
    );
    addText(`Risk Score: ${Math.round(confidence * 100)}%`, 12);
    addText(`Model Label: ${label}`, 12);
    addText(`Confidence: ${(confidence * 100).toFixed(1)}%`, 12);
    addSeparator();

    // Add transcription segments
    if (transcriptData.transcription && transcriptData.transcription.length > 0) {
      addHeading("Transcription");

      const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
      };

      transcriptData.transcription.forEach((segment: any) => {
        ensureSpace(15);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(11);
        doc.text(
          `Speaker ${segment.speaker} [${formatTime(segment.start_time)} - ${formatTime(segment.end_time)}]`,
          margin,
          y
        );
        y += 6;

        // Split long text into multiple lines
        doc.setFont("helvetica", "normal");
        doc.setFontSize(11);
        const lines = doc.splitTextToSize(segment.text, 180);
        lines.forEach((line: string) => {
          ensureSpace();
          doc.text(line, margin, y);
          y += 6;
        });

        y += 4;
      });
    }

    // Get PDF as buffer
    const pdfOutput = doc.output("arraybuffer");
    const buffer = Buffer.from(pdfOutput);

    return new NextResponse(buffer, {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="transcript-${transcriptId}.pdf"`,
      },
    });
  } catch (error) {
    console.error("Error generating PDF:", error);
    return NextResponse.json(
      {
        error: "Failed to generate PDF",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}

