# 山西冬小麦 春旱×灌溉 稳健性扫描

目标: 现有样本能否做出显著交互。

 thr        extreme  irr  yearFE   N   main  main_p  x_irr  x_irr_p
 100 spring_cdd_max cont    True 233 -0.079   0.109  0.068    0.134
 100 spring_cdd_max cont   False 233 -0.101   0.003  0.076    0.059
 100 spring_cdd_max  grp    True 233 -0.030   0.182 -0.026    0.541
 100 spring_cdd_max  grp   False 233 -0.048   0.000 -0.033    0.373
 100  spring_precip cont    True 233  0.030   0.212 -0.042    0.102
 100  spring_precip cont   False 233  0.061   0.000 -0.058    0.002
 100  spring_precip  grp    True 233  0.001   0.888  0.015    0.462
 100  spring_precip  grp   False 233  0.020   0.001  0.017    0.277
 300 spring_cdd_max cont    True 195 -0.096   0.136  0.084    0.100
 300 spring_cdd_max cont   False 195 -0.111   0.005  0.091    0.044
 300 spring_cdd_max  grp    True 195 -0.036   0.280 -0.036    0.497
 300 spring_cdd_max  grp   False 195 -0.049   0.001 -0.042    0.362
 300  spring_precip cont    True 195  0.027   0.348 -0.052    0.073
 300  spring_precip cont   False 195  0.066   0.001 -0.064    0.004
 300  spring_precip  grp    True 195 -0.005   0.658  0.022    0.373
 300  spring_precip  grp   False 195  0.020   0.002  0.021    0.282
 500 spring_cdd_max cont    True 183 -0.098   0.146  0.086    0.115
 500 spring_cdd_max cont   False 183 -0.114   0.006  0.093    0.053
 500 spring_cdd_max  grp    True 183 -0.039   0.279 -0.037    0.514
 500 spring_cdd_max  grp   False 183 -0.050   0.001 -0.044    0.381
 500  spring_precip cont    True 183  0.019   0.567 -0.055    0.089
 500  spring_precip cont   False 183  0.073   0.001 -0.073    0.004
 500  spring_precip  grp    True 183 -0.013   0.293  0.026    0.339
 500  spring_precip  grp   False 183  0.021   0.002  0.029    0.216

解读: x_irr>0 且 x_irr_p<0.05 => 灌溉缓解春旱 (雨养脆弱)。
