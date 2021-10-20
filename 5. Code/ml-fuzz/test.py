from mlfuzz import fuzzer
target = "/home/zys/fuzz/libpng-afl/pngimage"
input_dir = "/home/zys/AFL/testcases/images/png"
output_dir = "./afl-output"
timeout = 10000
fuzzer.setup(target, input_dir, output_dir, timeout)

for i in range(18):
    print(fuzzer.get_seed())
    x, _ = fuzzer.gen_x(10000)
    print(x.shape)