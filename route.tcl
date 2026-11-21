# vivado -mode batch -source route.tcl -tclargs PART CLOCK_PERIOD_NS
if {$argc != 2} {error "Pass FPGA part and clock period in ns"}
set part [lindex $argv 0]
set period [lindex $argv 1]
file mkdir reports
read_verilog -sv dpd.sv
synth_design -top dpd -part $part -mode out_of_context
create_clock -name core -period $period [get_ports clk]
opt_design
place_design
route_design
report_utilization -file reports/utilization.rpt
report_timing_summary -report_unconstrained -file reports/timing.rpt
report_power -file reports/power.rpt
write_checkpoint -force reports/dpd_routed.dcp
