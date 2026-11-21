module tb;
    logic clk=0, rst=1, cfg_we=0, s_valid=0, s_last=0, m_ready=0;
    logic [2:0] cfg_addr;
    logic [31:0] cfg_data, s_data, m_data;
    logic s_ready, m_valid, m_last;
    dpd dut(.*);
    always #5 clk = !clk;
    localparam N = 64*(512+32);
    logic [31:0] stim[0:N-1], expected[0:N-1], coeff[0:5];
    int sent=0, seen=0, fh;
    logic held=0;
    logic [32:0] held_output;
    initial begin
        $readmemh("out/input.hex", stim);
        $readmemh("out/expected.hex", expected);
        $readmemh("out/coeff.hex", coeff);
        fh = $fopen("out/rtl.hex","w");
        if (fh == 0) $fatal(1,"open output failed");
        repeat(3) @(negedge clk);
        rst=0;
        for (int k=0;k<6;k++) begin
            cfg_we=1; cfg_addr=3'(k); cfg_data=coeff[k]; @(negedge clk);
        end
        cfg_we=0;
        while (seen < N) begin
            s_valid = sent < N;
            if (s_valid) begin s_data=stim[sent]; s_last=(sent==N-1); end
            m_ready = ($urandom_range(3) != 0);
            @(posedge clk);
            if (held && (!m_valid || {m_last,m_data} !== held_output))
                $fatal(1,"output changed during stall");
            held=m_valid && !m_ready; held_output={m_last,m_data};
            if (s_valid && s_ready) sent++;
            if (m_valid && m_ready) begin
                if (m_data !== expected[seen] || m_last !== (seen==N-1))
                    $fatal(1,"sample %0d got %h expected %h",seen,m_data,expected[seen]);
                $fdisplay(fh,"%08x",m_data);
                seen++;
            end
            @(negedge clk);
        end
        $fclose(fh); $display("PASS %0d samples",seen); $finish;
    end
    initial begin #10000000; $fatal(1,"timeout"); end
endmodule
