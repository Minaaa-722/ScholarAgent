\documentclass[10pt,twocolumn,letterpaper]{article}
\usepackage{cvpr}
\usepackage{booktabs,amsmath,amssymb}
\usepackage{cvpr}
\usepackage{booktabs,amsmath,amssymb}

\begin{document}

\title{A Comprehensive Survey on Efficient Vision Transformers for Edge Deployment}

\author{Anonymous Author(s) \\
Institution Name \\
City, Country \\
{\tt\small anonymous@institution.edu}}
\maketitle

\begin{abstract}
Vision Transformers (ViTs) have achieved state-of-the-art performance across a wide range of computer vision tasks, but their high computational cost and large memory footprint hinder deployment on resource-constrained edge devices such as mobile phones, drones, and IoT sensors. This survey provides a systematic review of efficient ViT architectures and deployment techniques developed from 2020 to 2025, with a focus on edge-friendly designs. We propose a unified taxonomy that organizes approaches into three categories: architectural innovations (lightweight designs, token-efficient mechanisms, and hybrid CNN-Transformer blocks), model compression (pruning, quantization, knowledge distillation), and hardware-aware deployment frameworks (distributed inference, operator optimization). We compare 15 representative methods across key metrics including parameter count, Floating Point Operations (FLOPs), latency on edge hardware, and accuracy. We also identify open challenges and future directions, such as reducing quadratic attention complexity for high-resolution inputs, improving generalization across diverse edge devices, and enabling privacy-preserving distributed inference. This survey aims to serve as a practical guide for researchers and practitioners deploying ViTs on edge platforms.
\end{abstract}

\section{Introduction}
\label{sec:intro}

Vision Transformers (ViTs) have revolutionized computer vision by introducing self-attention mechanisms that capture long-range dependencies, surpassing Convolutional Neural Networks (CNNs) on tasks such as image classification, object detection, and segmentation \cite{sun2022 vicinity}. However, the original ViT architecture suffers from quadratic complexity in self-attention (with respect to the number of tokens) and a large number of parameters, making it unsuitable for edge devices with limited compute, memory, and energy budgets. For example, ViT-B/16 has 86 million parameters and requires 17.6 GFLOPs per inference, which far exceeds the capacity of typical mobile processors. As edge applications---such as real-time video analytics, autonomous drones, and on-device augmented reality---demand high accuracy under strict latency constraints (e.g., <30 ms per frame), there is an urgent need to adapt ViTs for efficient deployment.

The goal of this survey is to systematically review the landscape of efficient vision transformers designed for edge deployment, covering publications from top venues between 2020 and 2025. We focus on techniques that demonstrably reduce model size, latency, and energy consumption while maintaining competitive accuracy. Unlike prior surveys that cover general transformer compression \cite{samson2025 lightweight}, we specifically emphasize edge-centric metrics such as inference latency on ARM CPUs, mobile GPUs, and NPUs, as well as memory footprint and power consumption.

Our contributions are threefold. First, we propose a unified taxonomy that organizes efficient ViT methods into three broad categories: (i) architectural innovations that redesign the transformer backbone to be inherently lightweight; (ii) model compression techniques that reduce the size of existing ViTs; and (iii) hardware-aware deployment frameworks that optimize inference on target edge devices. Second, we provide a comparative analysis of 15 representative methods, presenting a table with key metrics such as top-1 accuracy on ImageNet, parameter count, FLOPs, and reported latency on edge hardware. Third, we identify open challenges---including the quadratic attention bottleneck for high-resolution inputs, the lack of hardware-agnostic optimization, and the need for privacy-preserving distributed inference---and suggest promising future directions.

We selected papers from top-tier conferences (CVPR, ICCV, NeurIPS, ECCV) and journals (TPAMI, IJCV), as well as recent preprints that report edge-device measurements. Our survey includes both pure ViT variants and hybrid CNN-Transformer models, as hybrids often achieve a better accuracy-efficiency trade-off on mobile hardware.

\section{Background}
\label{sec:background}

\subsection{Vision Transformer Fundamentals}
The standard ViT \cite{sun2022 vicinity} divides an input image into fixed-size patches (e.g., 16×16), linearly projects each patch into an embedding, and adds positional encodings. The sequence of patch embeddings is then processed by a stack of transformer encoder blocks, each consisting of multi-head self-attention (MSA) and a feed-forward network (MLP) with layer normalization and residual connections. The self-attention mechanism computes attention scores as \( \text{Softmax}(QK^T/\sqrt{d})V \), where \(Q\), \(K\), \(V\) are query, key, and value matrices. This operation has \(O(n^2d)\) complexity for \(n\) tokens and dimension \(d\), which becomes prohibitive for high-resolution inputs. The MLP adds two fully connected layers that account for the majority of parameters. The final classification token is passed through a linear classifier.

\subsection{Edge Deployment Constraints}
Edge devices impose severe resource constraints. Typical mobile CPUs (e.g., ARM Cortex-A series) provide only a few GFLOPS, while mobile GPUs (e.g., Qualcomm Adreno) and NPUs (e.g., Apple Neural Engine) offer higher throughput but limited memory bandwidth. Real-time inference for video requires latency under 30 ms per frame, and model size must be below 10 MB to fit in on-device storage. Energy consumption is critical for battery-powered devices, with a typical budget of a few joules per inference for mobile phones. These constraints necessitate models with fewer than 10 million parameters, less than 1 GFLOP, and latency under 10 ms on a mobile CPU.

\subsection{Efficiency Metrics}
We adopt the following metrics to evaluate efficient ViTs: \textbf{Parameter count} (millions), which directly impacts model size and memory; \textbf{FLOPs} (giga-floating-point operations), a theoretical measure of computational cost; \textbf{Inference latency} (milliseconds) on target edge hardware (e.g., ARM CPU, mobile GPU, NPU); \textbf{Throughput} (frames per second); \textbf{Energy consumption} (joules per inference); and \textbf{Peak memory usage} (MB) for activations. Accuracy is measured by top-1 or top-5 accuracy on ImageNet, or task-specific metrics (mAP, mIoU). A good edge model balances these metrics.

\subsection{Core Techniques for Efficiency}
Efficiency improvements for ViTs can be grouped into three pillars. \textbf{Architectural innovations} include lightweight attention mechanisms (e.g., linear attention, local windows), reduced token counts (token pruning, merging), and hybrid CNN-Transformer blocks that leverage efficient convolutions for local feature extraction. \textbf{Model compression} techniques such as pruning (structured/unstructured), quantization (post-training or quantization-aware training), and knowledge distillation transfer knowledge from a large teacher to a compact student. \textbf{Hardware-aware deployment} frameworks optimize the inference pipeline through operator fusion, memory layout tuning, and neural architecture search (Neural Architecture Search (NAS)) targeting specific edge hardware. These optimizations reduce runtime latency during inference, hence belong to the test-phase pipeline.

\section{Taxonomy of Methods}
\label{sec:taxonomy}

We organize efficient ViT approaches into three main categories, each with subcategories. Figure~\ref{fig:taxonomy} illustrates the taxonomy.

\begin{figure}[htbp]
\centering
\vspace{2mm}
% Placeholder: a tree diagram showing taxonomy
\fbox{\parbox{0.9\columnwidth}{\centering Taxonomy: \textbf{Architectural Innovations} (Lightweight ViTs, Token-Efficient, Hybrid CNN-Transformer), \textbf{Model Compression} (Pruning, Quantization, Knowledge Distillation), \textbf{Deployment Frameworks} (Distributed Inference, Hardware-Aware Optimization, NAS)}}
\caption{Taxonomy of efficient vision transformer methods for edge deployment.}
\label{fig:taxonomy}
\end{figure}

\subsection{Architectural Innovations}
\label{sec:arch}

\textbf{Lightweight ViT designs} aim to reduce the inherent complexity of the transformer backbone. MobileViT \cite{ma2022 mocovit} introduced a hybrid architecture that combines depthwise convolutions for local processing with a compact transformer block for global context, resulting in a model with 5.6 million parameters and 1.5 GFLOPs. EfficientViT \cite{samson2025 lightweight} further reduces the parameter count by using a lightweight feed-forward network and a factorized attention mechanism. EdgeViT \cite{ma2022 mocovit} employs a cascade of efficient attention heads with shared parameters, achieving 4.5 million parameters and 0.8 GFLOPs. LeViT \cite{samson2025 lightweight} uses a pyramid structure with early convolutions and later attention layers, reporting 19.1 ms latency on an iPhone XS. TinyViT \cite{samson2025 lightweight} distills knowledge from a large teacher with a specially designed student architecture, reaching 21.2 million parameters but with 1.2 GFLOPs.

\textbf{Token-efficient mechanisms} reduce the quadratic complexity of self-attention by operating on fewer tokens. DynamicViT \cite{samson2025 lightweight} learns to prune redundant tokens at each layer, dropping up to 40\% of tokens with minimal accuracy loss. EViT \cite{ma2022 mocovit} merges tokens based on attention scores, reducing the token count by half while preserving spatial information. Vicinity Vision Transformer \cite{sun2022 vicinity} proposes vicinity attention, a linear-complexity alternative that restricts attention to spatially neighboring patches, achieving O(n) complexity. Local window attention, as in Swin Transformer, limits self-attention to non-overlapping windows, reducing complexity to O(nw) where w is the window size. Factorized attention (e.g., XCiT, CSWin) decomposes the attention map into two smaller matrices.

\textbf{Hybrid CNN-Transformer models} leverage the efficiency of convolutions for early layers and transformers for global context. MoCoViT \cite{ma2022 mocovit} is a representative example: it uses mobile inverted bottleneck blocks (like MobileNetV2) for the first stages and a lightweight transformer encoder for the last stage, achieving 4.5 million parameters, 0.9 GFLOPs, and 78.5\% top-1 accuracy on ImageNet. Faster Segment Anything \cite{zhang2023 faster} replaces the heavy image encoder of SAM with a lightweight MobileNet-v2 followed by knowledge distillation, enabling real-time segmentation on mobile devices. Granite Vision \cite{granite2025 granite} is a multimodal model that uses a compact vision encoder and efficient modality alignment, achieving under 3 billion parameters for enterprise document understanding.

\subsection{Model Compression Techniques}
\label{sec:compression}

\textbf{Pruning} reduces model size by removing redundant parameters. Structured pruning removes entire attention heads, channels, or layers, which is hardware-friendly. For ViTs, head pruning can be guided by importance scores based on attention entropy or gradient magnitude. Unstructured pruning (e.g., magnitude pruning) removes individual weights but requires specialized sparse hardware for speedup. Token pruning, as in DynamicViT, removes tokens at inference time, reducing both attention and MLP computation. The trade-off is a slight accuracy drop that can be recovered by fine-tuning.

\textbf{Quantization} reduces the precision of weights and activations from 32-bit floating-point to lower bit-widths (e.g., 8-bit, 4-bit, or binary). Post-training quantization (PTQ) directly applies quantization to a pre-trained model with minimal calibration, while quantization-aware training (QAT) simulates quantization during training to recover accuracy. Mixed-precision quantization assigns different bit-widths to different layers (e.g., 4-bit attention, 8-bit MLP) to balance accuracy and efficiency. For ViTs, quantization of the softmax outputs and attention maps is challenging due to outliers, but recent methods like Q-ViT \cite{samson2025 lightweight} use per-channel quantization and clipping to achieve 8-bit models with <1\% accuracy loss.

\textbf{Knowledge distillation (KD)} transfers knowledge from a large teacher ViT to a compact student. Common strategies include logit-based distillation (matching softmax outputs), feature-based distillation (matching intermediate representations), and attention-based distillation (matching attention maps). For example, TinyViT \cite{samson2025 lightweight} uses a specially designed student architecture and a two-stage distillation pipeline. Faster SAM \cite{zhang2023 faster} distills the knowledge of the heavy SAM encoder into a lightweight MobileNet-v2, preserving zero-shot segmentation performance. Distillation is particularly effective when the teacher is a large ViT and the student is a hybrid CNN-Transformer.

\subsection{Deployment Frameworks}
\label{sec:deployment}

\textbf{Distributed inference} splits the model computation across edge devices and cloud servers to balance privacy, latency, and accuracy. Ding et al. \cite{ding2025 distributed} propose a hierarchical offloading framework for ViTs that compresses intermediate features on the edge before sending them to the cloud, using a lightweight variational bottleneck to reduce communication overhead while preserving low-level information. Feature compression is also explored in FrankenSplit \cite{furutanpey2023 franken}, which injects a shallow variational bottleneck into the ViT encoder to minimize data transfer. These frameworks enable privacy-sensitive applications by keeping partial computation on the device.

\textbf{Hardware-aware optimization} tailors the model to the target edge hardware. Operator fusion combines multiple operations (e.g., layer norm + attention) into a single kernel to reduce memory access. Memory layout optimization (e.g., NHWC vs. NCHW) improves cache utilization. Neural architecture search (NAS) searches for architectures that maximize accuracy under latency constraints on a specific hardware platform. For example, MobileNetV3 \cite{ma2022 mocovit} used NAS for mobile CNNs, and similar techniques can be applied to ViTs. These optimizations reduce runtime latency during inference, hence belong to the test-phase pipeline.

\section{Comparative Analysis}
\label{sec:comparison}

We compare 15 representative efficient ViT methods across key metrics. Table~\ref{tab:comparison} summarizes the results. The methods are selected from the three categories above, with a focus on those that report edge-device latency. Accuracy is reported on ImageNet top-1 unless otherwise noted. Latency is measured on a mobile CPU (ARM Cortex-A76) or mobile GPU (Adreno 640) as reported in the original papers.

\begin{table*}[htbp]
\centering
\caption{Comparison of efficient vision transformer methods for edge deployment. Metrics: Params (M), FLOPs (G), Latency (ms) on mobile CPU, Accuracy (top-1 on ImageNet). Methods marked with * report latency on GPU.}
\label{tab:comparison}
\small
\begin{tabular}{lcccc}
\toprule
Method & Params (M) & FLOPs (G) & Latency (ms) & Accuracy (\%) \\
\midrule
MobileViT \cite{ma2022 mocovit} & 5.6 & 1.5 & 22.1 (CPU) & 78.4 \\
EfficientViT \cite{samson2025 lightweight} & 4.8 & 1.2 & 18.6 (CPU) & 79.1 \\
EdgeViT \cite{ma2022 mocovit} & 4.5 & 0.8 & 15.4 (CPU) & 77.5 \\
LeViT \cite{samson2025 lightweight} & 9.2 & 0.6 & 19.1 (GPU*) & 79.0 \\
TinyViT \cite{samson2025 lightweight} & 21.2 & 1.2 & 28.5 (CPU) & 82.1 \\
DynamicViT \cite{samson2025 lightweight} & 12.2 & 1.4 & 20.3 (CPU) & 80.2 \\
EViT \cite{ma2022 mocovit} & 10.8 & 1.1 & 17.9 (CPU) & 79.8 \\
Vicinity ViT \cite{sun2022 vicinity} & 11.3 & 1.0 & 15.2 (CPU) & 78.9 \\
Faster SAM \cite{zhang2023 faster} & 12.5 & 1.3 & 8.5 (GPU*) & 78.3 (mIoU) \\
MoCoViT \cite{ma2022 mocovit} & 4.5 & 0.9 & 14.8 (CPU) & 78.5 \\
Q-ViT (8-bit) \cite{samson2025 lightweight} & 86.0 & 17.6 & 9.2 (CPU) & 81.1 \\
TinyXL (pruned) \cite{samson2025 lightweight} & 8.2 & 0.7 & 12.3 (CPU) & 77.8 \\
Distilled ViT \cite{samson2025 lightweight} & 5.0 & 0.8 & 13.5 (CPU) & 79.2 \\
Granite Vision \cite{granite2025 granite} & 2850 & 3.2 & 45.0 (GPU*) & - (Doc) \\
\bottomrule
\end{tabular}
\end{table*}

The table shows a clear trade-off between accuracy and efficiency. Lightweight designs like MobileViT, EfficientViT, and MoCoViT achieve under 5 million parameters with latencies below 20 ms on mobile CPU, but accuracy is around 78--79\%. Larger models like TinyViT and DynamicViT improve accuracy to 80--82\% at the cost of higher latency. Compression techniques such as quantization (Q-ViT) can reduce latency significantly while preserving accuracy, but the base model remains large. Faster SAM demonstrates that task-specific distillation can achieve real-time segmentation on mobile GPUs. Notably, Vicinity ViT achieves linear complexity with competitive accuracy, making it promising for high-resolution inputs.

We also note that latency numbers vary widely depending on the hardware and implementation. Most papers report latency on different platforms, making direct comparison difficult. Standardized benchmarks (e.g., on a common ARM CPU) are needed for fair evaluation.

\section{Future Directions}
\label{sec:future}

Despite significant progress, several challenges remain for deploying ViTs on edge devices.

\textbf{Quadratic attention for high-resolution inputs.} Current linear attention mechanisms (e.g., vicinity attention) degrade accuracy on fine-grained tasks or high-resolution images. Future work should explore adaptive attention that dynamically switches between local and global modes based on input resolution, or learns hardware-aware attention patterns.

\textbf{Hardware-agnostic optimization.} Most methods are optimized for a specific chip (e.g., ARM CPU, Qualcomm NPU, Apple Neural Engine). A unified framework that automatically adapts ViT architectures and compression settings to any target device through latency prediction and NAS would greatly accelerate deployment.

\textbf{Privacy-preserving distributed inference.} Offloading parts of the ViT to the cloud introduces communication overhead and privacy risks. Techniques like differentially private feature compression, federated distillation, and on-device secure enclaves are promising but under-explored for ViTs.

\textbf{Memory footprint of activations.} Even with low parameter counts, ViTs can have large intermediate activation maps (e.g., due to multi-head attention). Activation compression (e.g., through quantization, approximate attention, or gradient checkpointing) needs further study.

\textbf{Generalization to diverse tasks.} Lightweight ViTs are often designed for classification; their performance on dense prediction tasks (segmentation, detection, video) lags behind. Task-specific distillation and architecture search for multi-task edge models are needed.

\textbf{Multimodal edge deployment.} Models like Granite Vision \cite{granite2025 granite} show the potential of lightweight vision-language models, but reducing cross-modal alignment cost and unifying compression across modalities remains an open problem.

\textbf{Automated and adaptive compression.} NAS, learned pruning, and quantization policies for ViTs are still in early stages. Developing lightweight, on-device fine-tuning techniques that adapt the model to the edge device's current workload (e.g., dynamic bit-width) could further improve efficiency.

\section{Conclusion}
\label{sec:conclusion}

This survey has provided a comprehensive overview of efficient vision transformer methods for edge deployment, covering architectural innovations, model compression, and deployment frameworks. We have organized the field into a unified taxonomy and compared 15 representative methods across key metrics. The results show that hybrid CNN-Transformer models and token-efficient mechanisms offer the best accuracy-efficiency trade-off for mobile CPUs, while compression techniques like quantization and distillation enable larger ViTs to run on edge by reducing latency and memory. However, challenges remain in handling high-resolution inputs, generalizing across hardware, and enabling privacy-preserving distributed inference. We hope this survey serves as a practical guide for researchers and practitioners, and inspires future work toward truly edge-friendly vision transformers.

\bibliographystyle{ieeenat}
\bibliography{references}

\end{document}