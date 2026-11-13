# Vo mong: moi logic nam trong tasks.py (Windows khong co make -> goi thang `python tasks.py <lenh>`).
.PHONY: setup test lint check
setup test lint check:
	python tasks.py $@
