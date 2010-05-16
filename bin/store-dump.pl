use Data::Dumper;
use Storable qw(store);

my $from_file_name = shift or die;
my $to_file_name = shift or die;

my $data = do $from_file_name;
store $data => $to_file_name;
