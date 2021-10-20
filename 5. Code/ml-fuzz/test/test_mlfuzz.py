import unittest
from mlfuzz import fuzzer


class TestFuzzerSetup(unittest.TestCase):

    target = None
    input_dir = None
    output_dir = None
    timeout = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.target = "/home/zys/fuzz/libpng-afl/pngimage"
        cls.input_dir = "/home/zys/AFL/testcases/images/png"
        cls.output_dir = "./afl-output"
        cls.timeout = 10000
        fuzzer.setup(cls.target, cls.input_dir, cls.output_dir, cls.timeout)

    @unittest.skip
    def test_setup(self):
        print(fuzzer.get_argv())

    def test_gen_seed(self):
        for i in range(18):
            print(fuzzer.get_seed())
            x, _ = fuzzer.gen_x(10000)
            print(x.shape)


if __name__ == '__main__':
    unittest.main()
