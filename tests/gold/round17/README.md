# 第17轮第一阶段真人金标

真实清单文件名为 `manifest.json`，但在业务标注人完成、LEO仲裁并冻结以前不得创建通过性占位清单。`make phase2-round17-eval` 在文件缺失时必须返回非零。

固定版本为 `phase2-round17-gold-v1.0.0`，样本量为500个Document、300个重复/关系对、100个Event、200个Claim/Evidence和100个检索题。关键安全样本由yinzi和baixuejiao双盲标注，全部分歧由LEO仲裁；数字样本由baixuejiao主标，yinzi至少盲复标20%。清单不得保存未经授权的正文，只保存稳定ID、授权证据引用、标签及内容哈希。
