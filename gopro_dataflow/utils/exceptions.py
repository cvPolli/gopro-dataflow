class GnssGapExceedsLimit(Exception):
    def __init__(self, gap, limit):
        self.gap = gap
        self.limit = limit
        super().__init__(f"GNSS gap ({gap} meters) exceeds distance without GNSS limit ({limit} metrs)")

class QualityPercentageExceedsLimit(Exception):
    def __init__(self, quality_percentage, limit):        
        self.quality_percentage = quality_percentage
        self.limit = limit
        super().__init__(f"Quality percentage ({quality_percentage}%) exceeds percentage limit ({limit}%)")
