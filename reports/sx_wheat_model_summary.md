# 山西冬小麦 极端气候×灌溉率 交互(首版)

样本 183 县域年, 38 县, 2019-2023

DV=log(单产) | 县FE+年FE | 聚类县标准误

          extreme   main  main_p  x_irr  x_irr_p   n
   spring_cdd_max -0.098   0.146  0.086    0.115 183
    spring_precip  0.019   0.567 -0.055    0.089 183
  grain_heat_days  0.072   0.225 -0.036    0.347 183
spring_frost_late  0.022   0.279 -0.005    0.751 183

解读: x_irr>0 且显著 => 灌溉率越高, 该极端对单产的负向影响越弱, 即雨养更脆弱。
