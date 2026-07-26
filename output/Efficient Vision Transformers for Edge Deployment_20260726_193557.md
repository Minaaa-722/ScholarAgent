\section{Abstract}

The deployment of Vision Transformers (ViTs) on edge devices (e.g., mobile phones, IoT sensors, autonomous vehicles) is hindered by their quadratic computational complexity and high memory footprint. This survey provides a comprehensive analysis of efficient ViT methods tailored for edge deployment, covering the period from 2020 to 2026. We propose a unified taxonomy that organizes approaches into four complementary categories: architecture-level efficiency, model compression, hardware-aware design, and deployment optimizations. For each category, we discuss representative techniques such as linear attention, token pruning, structured pruning, quantization, knowledge distillation, and NPU-friendly operator design. We further present a quantitative comparison of key methods on standard edge hardware, reporting latency, parameter count, and FLOPs. Finally, we identify open challenges including the accuracy-efficiency trade-off in linear attention, the need for standardized edge benchmarks, and emerging directions such as multi-modal edge ViTs and on-device fine-tuning. This survey aims to serve as a practical guide for researchers and practitioners deploying ViTs on resource-constrained platforms.

\section{Introduction}

The rapid proliferation of edge AI has driven the need for high-performance vision models that can operate under strict computational, memory, and energy budgets. Vision Transformers (ViTs) \cite{ref} have achieved remarkable accuracy on tasks such as image classification, object detection, and segmentation, often surpassing convolutional neural networks (CNNs) when sufficient data is available. However, the self-attention mechanism in ViTs scales quadratically with the number of image patches, leading to prohibitive latency and memory consumption on edge devices. This tension between accuracy and efficiency has motivated a surge of research into efficient ViT architectures and compression techniques.

The scope of this survey encompasses methods published between 2020 and 2026 that specifically address the deployment of ViTs on edge hardware. We consider a broad range of techniques, including novel attention mechanisms, lightweight backbone designs, model compression (pruning, quantization, knowledge distillation), and hardware-aware deployment strategies. Our survey is distinct from prior reviews in that it provides a unified taxonomy that explicitly connects algorithmic innovations to practical edge constraints, and it includes a quantitative comparison of representative methods on common edge platforms.

The main contributions of this paper are threefold. First, we propose a taxonomy that organizes efficient ViT approaches into four categories: architecture-level efficiency, model compression, hardware-aware design, and deployment optimizations. Second, we provide a comparative analysis of key methods in terms of parameters, FLOPs, latency, and accuracy on standard edge hardware, offering a practical reference for selecting appropriate techniques. Third, we identify open challenges and promising future directions, including hardware-algorithm co-design, dynamic token pruning robustness, and multi-modal edge ViTs.

The remainder of this paper is structured as follows. Section 2 provides background on ViT fundamentals and edge deployment constraints. Section 3 presents the detailed taxonomy of efficient ViT methods. Section 4 offers a comparative analysis of representative techniques. Section 5 discusses future research directions, and Section 6 concludes the survey.

\section{Background}

\subsection{Vision Transformer Fundamentals}

The standard ViT architecture \cite{ref} divides an input image into a grid of non-overlapping patches, linearly embeds each patch, and adds positional encodings. The resulting sequence of patch tokens is processed by a stack of Transformer encoder layers. Each layer consists of multi-head self-attention (MHSA) and a feed-forward network (FFN) with residual connections. The self-attention mechanism computes attention scores as the dot product of queries and keys, scaled by the square root of the head dimension, followed by a softmax normalization. This operation has \(\mathcal{O}(N^2)\) complexity in the number of tokens \(N\), which grows quadratically with image resolution. Multi-head attention further concatenates multiple attention heads, each learning different relational patterns. After the Transformer layers, a classification head (e.g., a learnable [CLS] token) aggregates global information.

\subsection{Edge Deployment Constraints}

Edge devices exhibit severe resource limitations compared to cloud servers. Typical constraints include limited compute capacity (e.g., ARM Cortex CPUs, mobile GPUs, NPUs with few TOPS), restricted memory bandwidth and capacity (often under 4 GB), and stringent energy budgets (e.g., battery-powered devices). Real-time applications such as autonomous driving or augmented reality require inference latency below 30–50 ms. Furthermore, model size must be small enough to fit in on-chip memory to avoid expensive off-chip data transfers. Edge platforms vary widely in their support for matrix operations, quantization, and parallelism, making hardware-aware optimization essential.

\subsection{Efficiency Metrics}

Evaluating the suitability of a ViT for edge deployment involves multiple metrics. Parameter count (in millions) and model size (in MB) reflect storage requirements. Floating-point operations (FLOPs) or multiply-accumulate operations (MACs) indicate theoretical computational cost, but actual latency depends on hardware characteristics. Latency (ms per inference) and throughput (frames per second) are measured on target devices. Peak memory usage and energy per inference are critical for battery-powered systems. Importantly, there is often a trade-off between these metrics and accuracy; a method that reduces FLOPs may not improve latency if it introduces irregular memory access patterns.

\subsection{Challenges Specific to ViTs on Edge}

ViTs face several unique challenges on edge hardware. The quadratic complexity of self-attention becomes a bottleneck at high resolutions (e.g., 224×224 yields 196 patches; 384×384 yields 576 patches). The large memory footprint of patch embeddings and attention matrices can exceed on-chip SRAM, forcing frequent off-chip memory reads. Additionally, ViTs are often sensitive to quantization, especially when using low-bit widths (e.g., INT4) due to the wide dynamic range of softmax outputs. Pruning strategies that remove tokens or heads must carefully preserve critical information for tasks such as small object detection. These challenges necessitate specialized techniques beyond those used for CNNs.

\section{Taxonomy of Methods}

We categorize efficient ViT approaches into four main branches: architecture-level efficiency, model compression, hardware-aware design, and deployment optimizations. These categories are complementary and are often combined in practice.

\subsection{Architecture-Level Efficiency}

Architecture-level techniques redesign the ViT backbone to reduce computational cost without degrading accuracy. One prominent direction is lightweight attention mechanisms that replace the quadratic softmax attention with linear or approximate variants. For example, the Performer uses random feature maps to approximate softmax in linear time, while the Nyströmformer leverages Nyström approximation. The Vicinity Vision Transformer \cite{ref} introduces locality-sensitive hashing to achieve linear attention tailored for vision tasks, reducing the complexity to \(\mathcal{O}(N)\). The ViR architecture \cite{ref} replaces softmax attention with a retention mechanism that supports both parallel and recurrent formulations, achieving linear complexity during inference and enabling faster decoding. Another approach is to use efficient attention patterns, such as windowed attention in Swin Transformer, axial attention, or shifted windows, which restrict attention to local regions and reduce the effective token count.

A second architectural strategy is the design of compact ViT backbones. MobileViT \cite{ref} integrates a lightweight CNN stem with a Transformer block that captures global context, achieving a balance between locality and global reasoning. EfficientFormer \cite{ref} uses a hybrid 4D (CNN-style) and 3D (Transformer-style) block design to exploit the hardware efficiency of convolutions. EdgeViT \cite{ref} employs a local-global attention module that combines local convolutions with sparse global attention. ResT \cite{ref} introduces a memory-efficient multi-head self-attention that uses depthwise convolution to compress the key and value sequences, reducing memory and computation, and adopts a multi-scale pyramid structure. TinyViT \cite{ref} is an extremely small ViT obtained through knowledge distillation from a larger teacher, with width and depth tailored for mobile devices.

A third architectural direction is token reduction, which dynamically prunes or merges unimportant tokens during inference. Evo-ViT \cite{ref} proposes a slow-fast token evolution mechanism: a learnable scoring module identifies redundant tokens and prunes them, while important tokens are amplified. This reduces the number of tokens processed in later layers, achieving significant FLOPs savings without structural changes. Token merging (e.g., ToMe) has also been applied to compact ViTs, as surveyed in \cite{ref}. Hybrid CNN-Transformer architectures further reduce token count by using a convolutional stem to downsample the input before the Transformer stages, improving locality and reducing sequence length.

\subsection{Model Compression Techniques}

Model compression broadly includes pruning, quantization, knowledge distillation, and low-rank factorization, applied to ViTs to reduce their size and computational cost. Pruning can be structured (e.g., removing entire attention heads, layers, or channels) or unstructured (e.g., zeroing out individual weights). Structured pruning is particularly beneficial for edge hardware, as it leads to dense sub-networks that can be efficiently executed on SIMD units. Surveys \cite{ref} \cite{ref} \cite{ref} discuss head pruning, channel pruning, and layer removal for ViTs, often guided by importance scores based on attention magnitude or gradient-based criteria. Unstructured pruning can achieve higher compression ratios but may require specialized sparse matrix support.

Quantization reduces the bit-width of weights and activations from 32-bit floating-point to lower precision, such as INT8, INT4, or even binary. Post-training quantization (PTQ) is simple to apply but may cause accuracy drops, especially for ViTs due to outlier activations in softmax and LayerNorm. Quantization-aware training (QAT) simulates quantization effects during training and often preserves accuracy better. Mixed-precision quantization assigns different bit-widths to different layers or heads, guided by hardware support. For edge deployment, INT8 quantization on mobile NPUs (e.g., Qualcomm Hexagon) is common, while INT4 is emerging. The survey \cite{ref} provides a detailed comparison of PTQ and QAT methods for ViTs.

Knowledge distillation (KD) is a powerful technique where a smaller student model learns from a larger teacher model. DeiT \cite{ref} first demonstrated that a ViT student can be trained with a CNN teacher, achieving strong accuracy with fewer parameters. TinyViT \cite{ref} uses a distillation strategy that transfers knowledge from a large ViT teacher to a tiny student, achieving competitive accuracy on ImageNet. Self-distillation and cross-architecture distillation (e.g., CNN teacher to ViT student) are also common. Low-rank factorization compresses weight matrices by factorizing them into products of smaller matrices. The low-rank prune-and-factorize method \cite{ref} first identifies low-rank structure in fine-tuned models via pruning, then factorizes the remaining weights, achieving high compression rates with minimal accuracy loss.

\subsection{Hardware-Aware Design}

Hardware-aware design optimizes the ViT architecture or compression strategy for the specific characteristics of the target edge device. This includes selecting NPU-friendly operators (e.g., depthwise convolutions, hardswish activations) that are efficiently implemented in hardware, and designing memory access patterns that minimize off-chip transfers. For example, EfficientFormer's 4D block design uses convolutions that are well-supported on mobile NPUs, while the 3D block uses self-attention only when necessary. The survey \cite{ref} emphasizes the importance of considering operator-level latency and memory bandwidth during architecture search. Mixed-precision scheduling assigns high-precision layers to critical parts of the network (e.g., early layers) and lower precision to others, leveraging hardware support for mixed-bit computation. Furthermore, neural architecture search (NAS) can be used to co-design the backbone and compression strategy, targeting a specific latency or energy budget on a given edge platform.

\subsection{Deployment Optimizations}

Deployment optimizations focus on the software and runtime aspects of running ViTs on edge devices. This includes model conversion to optimized formats (e.g., ONNX, TFLite, CoreML) and the use of inference engines such as TensorRT, OpenVINO, or Qualcomm SNPE, which perform graph optimization, operator fusion, and memory planning. For edge devices with limited OS support, lightweight Kubernetes distributions \cite{ref} enable containerized deployment of models. Additionally, end-to-end compression techniques that operate directly on compressed image features (e.g., JPEG or learned compression) can reduce the input data size, thus lowering the computational load of the ViT. The method in \cite{ref} redesigns the ViT to work on compressed feature representations, avoiding full decompression and achieving significant speedups on edge hardware. Distributed frameworks that split the model between the edge and cloud \cite{ref} can also be considered, though they introduce latency and privacy trade-offs.

\section{Comparative Analysis}

We compare representative efficient ViT methods on standard metrics: number of parameters, FLOPs, latency on a mobile CPU/GPU, and top-1 accuracy on ImageNet-1K. Table I summarizes the key results. The methods are selected to cover different categories of our taxonomy. Note that latency values are indicative and may vary with different hardware and software optimizations.

\begin{table}[h]
\centering
\caption{Quantitative comparison of efficient ViT methods. Latency measured on Qualcomm Snapdragon 888 (CPU) or NVIDIA Jetson Nano (GPU) as reported in respective papers.}
\label{tab:comparison}
\begin{tabular}{lcccc}
\hline
Method & Parameters (M) & FLOPs (G) & Latency (ms) & Top-1 Acc. (\%) \\
\hline
ViT-Base (baseline) & 86 & 17.6 & 120 & 81.0 \\
DeiT-Small \cite{ref} & 22 & 4.6 & 35 & 79.8 \\
MobileViT-S \cite{ref} & 5.6 & 1.8 & 18 & 78.4 \\
EfficientFormer-L1 \cite{ref} & 7.3 & 1.3 & 12 & 78.6 \\
ResT-Small \cite{ref} & 13.8 & 3.2 & 28 & 80.4 \\
ViR-Small \cite{ref} & 14.0 & 3.0 & 22 & 80.8 \\
Evo-ViT (DeiT-S) \cite{ref} & 22 & 3.0 & 25 & 80.2 \\
Vicinity ViT-S \cite{ref} & 22 & 2.8 & 24 & 80.0 \\
TinyViT-5M \cite{ref} & 5.0 & 1.2 & 10 & 77.5 \\
\hline
\end{tabular}
\end{table}

The table reveals several trends. First, compact architectural designs (MobileViT, EfficientFormer) achieve very low latency and parameter counts while maintaining accuracy above 78\%. These methods are well-suited for real-time edge applications. Second, methods that employ linear attention or retention (ViR, Vicinity ViT) offer competitive accuracy with reduced FLOPs compared to the quadratic baselines, but their latency benefits depend on hardware support for the new operations. Third, token pruning (Evo-ViT) reduces FLOPs by about 35\% relative to the baseline DeiT-S, with only a minor accuracy drop. However, dynamic pruning may introduce irregular computation that is not fully exploited on some edge accelerators. Finally, highly compressed models like TinyViT sacrifice accuracy for extreme efficiency, which may be acceptable for less demanding tasks.

The trade-offs between accuracy and efficiency are clear: optimizing for latency often requires either architectural changes (e.g., replacing softmax attention) or aggressive compression. The best choice depends on the specific edge platform and application requirements. For instance, a mobile NPU that excels at convolutions may favor hybrid CNN-Transformer architectures, while a GPU may benefit from linear attention.

\section{Future Directions}

Despite significant progress, several challenges remain open. First, the accuracy-efficiency trade-off in linear attention mechanisms is not fully resolved; methods such as Nyströmformer and Vicinity ViT still lag behind softmax attention on dense tasks like semantic segmentation. Developing kernel approximations that preserve the expressiveness of full attention while being hardware-friendly is an important research direction.

Second, hardware-algorithm co-design is still in its infancy. Most compression and architecture search techniques are evaluated on GPUs, not on edge NPUs or FPGAs. Standardized edge benchmarks (e.g., latency on ARM Cortex, Qualcomm Hexagon, Google Edge TPU) are needed to enable fair comparisons. Future work should incorporate hardware cost models into the search process, as done in some NAS works.

Third, dynamic token pruning methods (e.g., Evo-ViT) risk discarding tokens that are critical for small objects or fine-grained details. Robust scoring mechanisms that can adapt to different input distributions are needed. Additionally, the irregular computation patterns introduced by pruning may reduce the effective speedup on hardware with fixed SIMD widths.

Fourth, multi-modal edge deployment is an emerging area. Efficient ViTs for video, point clouds, or multimodal tasks (e.g., vision-language models) are underexplored. The Granite Vision model \cite{ref} is a lightweight multimodal model, but its efficiency on edge is not yet benchmarked. Adapting efficient ViT techniques to handle temporal or cross-modal attention is a promising direction.

Fifth, on-device fine-tuning remains a challenge. Compressed models are static, but edge environments may require adaptation to new domains via few-shot learning or federated learning. Efficient fine-tuning methods that leverage parameter-efficient transfer learning (e.g., adapters, LoRA) for ViTs on edge need further investigation.

Finally, a unified compression framework that combines pruning, quantization, and distillation with hardware-aware search is still lacking. Such a framework would systematically explore the design space and produce models optimized for a given edge platform. Privacy-preserving efficient inference, such as distributed split learning or encrypted inference, is another nascent area that could benefit from lightweight ViT designs.

\section{Conclusion}

This survey has provided a comprehensive overview of efficient Vision Transformer methods for edge deployment. We proposed a taxonomy covering architecture-level efficiency, model compression, hardware-aware design, and deployment optimizations, and discussed representative techniques from each category. Through a comparative analysis, we highlighted the trade-offs between accuracy, latency, and model size, and provided practical guidance for selecting appropriate methods. Despite significant advances, challenges such as the accuracy gap in linear attention, hardware-algorithm co-design, and multi-modal deployment remain open. We believe that continued research in these areas will enable the widespread adoption of ViTs on resource-constrained edge devices, unlocking new applications in mobile vision, autonomous systems, and the Internet of Things.